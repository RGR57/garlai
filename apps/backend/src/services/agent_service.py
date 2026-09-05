from src.models.chat_response import (
    ChatResponse,
)
from src.models.cognitive_state import CognitiveState
from src.models.durable_execution import ExecutionRunStatus
from src.core.exceptions import GARLException

from src.models.conversation import (
    ConversationMessage,
)

from src.models.memory import (
    MemoryType,
)

from src.repositories.cognitive_state_repository import (
    CognitiveStateRepository,
)

from src.services.approval_service import (
    ApprovalService,
)

from src.services.cognitive_pipeline import (
    CognitivePipeline,
)
from src.services.durable_execution_service import DurableExecutionService

from src.services.knowledge_service import (
    KnowledgeService,
)

from src.services.memory_extractor import (
    MemoryExtractor,
)

from src.services.memory_service import (
    MemoryService,
)

from src.utils.logger import (
    logger,
)
class AgentService:

    APPROVAL_COMMANDS = {
        "approve",
        "yes",
        "confirm",
        "continue",
    }

    REJECTION_COMMANDS = {
        "reject",
        "deny",
        "cancel",
        "no",
    }

    def __init__(
        self,
        pipeline: CognitivePipeline,
        state_repository: CognitiveStateRepository,
        approval_service: ApprovalService,
        memory_service: MemoryService,
        knowledge_service: KnowledgeService,
        memory_extractor: MemoryExtractor,
        durable_execution_service: DurableExecutionService | None = None,
    ):

        self.pipeline = pipeline

        self.state_repository = (
            state_repository
        )

        self.approval_service = (
            approval_service
        )

        self.memory_service = (
            memory_service
        )

        self.knowledge_service = (
            knowledge_service
        )

        self.memory_extractor = (
            memory_extractor
        )
        self.durable_execution_service = durable_execution_service
    # ======================================================
    # PUBLIC ENTRYPOINT
    # ======================================================

    async def respond(
        self,
        conversation_id: str,
        messages: list[ConversationMessage],
        execution_id: str | None = None,
        approval_id: str | None = None,
    ) -> ChatResponse:

        if self.durable_execution_service is not None:
            return await self._respond_durable(
                conversation_id,
                messages,
                execution_id,
                approval_id,
            )

        state = self.state_repository.get_or_create(
            conversation_id
        )

        latest_message = (
            messages[-1].content.strip()
        )

        normalized = (
            latest_message.lower()
        )

        logger.info(
            "Conversation: %s",
            conversation_id,
        )

        logger.info(
            "Objective: %s",
            latest_message,
        )
        # ==================================================
        # PENDING APPROVAL
        # ==================================================

        if state.execution.approval_required:

            if (
                normalized
                in self.APPROVAL_COMMANDS
            ):

                response = (
                    await self.approval_service
                    .approve(
                        state.execution
                    )
                )

                state.final_response = (
                    response
                )

                self._save_state(
                    conversation_id,
                    state,
                )

                return ChatResponse(
                    response=response,
                    artifacts=state.artifacts,
                )

            if (
                normalized
                in self.REJECTION_COMMANDS
            ):

                response = (
                    await self.approval_service
                    .reject(
                        state.execution
                    )
                )

                state.final_response = (
                    response
                )

                self._save_state(
                    conversation_id,
                    state,
                )

                return ChatResponse(
                    response=response,
                    artifacts=state.artifacts,
                )

            return ChatResponse(
                response=(
                    "An action is waiting "
                    "for approval.\n\n"
                    "Reply with "
                    "'approve' or 'reject'."
                ),
                artifacts=state.artifacts,
            )
        # ==================================================
        # NEW OBJECTIVE
        # ==================================================

        state.objective = latest_message
        # ==================================================
        # MEMORY EXTRACTION
        # ==================================================

        extracted = (
            await self.memory_extractor.extract(
                latest_message
            )
        )

        logger.info(
            "Extracted %d memories.",
            len(extracted),
        )

        for item in extracted:

            try:

                memory_type = MemoryType(
                    item.get(
                        "memory_type",
                        MemoryType.CONTEXT.value,
                    )
                )

            except Exception:

                memory_type = (
                    MemoryType.CONTEXT
                )

            try:

                await self.memory_service.store(
                    conversation_id,
                    item.get(
                        "content",
                        "",
                    ),
                    memory_type=memory_type,
                    importance=item.get(
                        "importance",
                        0.5,
                    ),
                )

            except Exception as exc:

                logger.warning(
                    "Memory store failed: %s",
                    exc,
                )
        # ==================================================
        # MEMORY RETRIEVAL
        # ==================================================

        memories = (
            await self.memory_service
            .retrieve_relevant(
                conversation_id,
                latest_message,
                limit=5,
            )
        )

        state.memories = [
            memory.content
            for memory in memories
        ]

        logger.info(
            "Retrieved %d memories.",
            len(state.memories),
        )

        # ==================================================
        # KNOWLEDGE RETRIEVAL
        # ==================================================

        state.knowledge_context = (
            await self.knowledge_service.search_context(
                latest_message,
                limit=5,
            )
        )

        logger.info(
            "Retrieved %d knowledge characters.",
            len(
                state.knowledge_context
            ),
        )
        # ==================================================
        # COGNITIVE PIPELINE
        # ==================================================

        response = await self.pipeline.run(
            messages=messages,
            state=state,
            knowledge_context=(
                state.knowledge_context
            ),
        )
        # ==================================================
        # SAVE RESPONSE
        # ==================================================

        state.final_response = (
            response.response
        )

        state.artifacts = (
            response.artifacts
        )

        self._save_state(
            conversation_id,
            state,
        )

        return response

    async def _respond_durable(
        self,
        conversation_id: str,
        messages: list[ConversationMessage],
        execution_id: str | None,
        approval_id: str | None,
    ) -> ChatResponse:
        latest = messages[-1].content.strip()
        normalized = latest.lower()
        if execution_id is None:
            if normalized in self.APPROVAL_COMMANDS | self.REJECTION_COMMANDS:
                raise GARLException("Approval commands require an execution_id.", 400)
            capability_selection = self.pipeline.resolve_capabilities(latest)
            execution_context = {
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in messages
                ]
            }
            if capability_selection is not None:
                execution_context["capability_selection"] = (
                    capability_selection.to_execution_context()
                )
            run = await self.durable_execution_service.start(
                objective=latest,
                conversation_id=conversation_id,
                execution_context=execution_context,
            )
            state = CognitiveState(objective=run.objective)
            plan = await self.pipeline.create_validated_plan(
                messages,
                state,
                capability_selection,
            )
            await self.durable_execution_service.persist_validated_plan(
                run.execution_id,
                plan,
            )
            execution_id = run.execution_id

        decision = await self.durable_execution_service.prepare_resume(execution_id)
        if decision.planning_required:
            persisted_messages = self._persisted_messages(decision.run)
            state = CognitiveState(objective=decision.run.objective)
            capability_selection = self.pipeline.restore_capabilities(
                decision.run.objective,
                decision.run.execution_context,
            )
            plan = await self.pipeline.create_validated_plan(
                persisted_messages,
                state,
                capability_selection,
            )
            await self.durable_execution_service.persist_validated_plan(execution_id, plan)
            decision = await self.durable_execution_service.prepare_resume(execution_id)

        if decision.status is ExecutionRunStatus.WAITING_APPROVAL:
            if normalized in self.APPROVAL_COMMANDS:
                if approval_id is None:
                    raise GARLException("Approval requires an approval_id.", 400)
                try:
                    result = await self.approval_service.approve_durable(
                        execution_id,
                        approval_id,
                        decision.execution_state,
                        finalize=False,
                    )
                except (KeyError, ValueError) as exc:
                    raise GARLException(str(exc), 409) from exc
                latest = await self.durable_execution_service.prepare_resume(execution_id)
                evaluation = self.pipeline.evaluate_execution_objective(
                    latest.run.objective,
                    latest.execution_state,
                    await self.durable_execution_service.objective_evaluation_context(
                        execution_id
                    ),
                )
                response = str(result.output) if result.success else (result.error or "Execution failed.")
                if evaluation is not None and not latest.may_execute:
                    if evaluation.complete:
                        await self.durable_execution_service.complete_if_finished(execution_id)
                    elif latest.status is ExecutionRunStatus.RUNNING:
                        await self.durable_execution_service.fail_if_finished(execution_id)
                        response = "Objective incomplete: " + "; ".join(evaluation.gaps)
                    latest = await self.durable_execution_service.prepare_resume(execution_id)
                return self._durable_response(
                    response,
                    latest.run,
                )
            if normalized in self.REJECTION_COMMANDS:
                if approval_id is None:
                    raise GARLException("Rejection requires an approval_id.", 400)
                try:
                    response = await self.approval_service.reject_durable(execution_id, approval_id)
                except (KeyError, ValueError) as exc:
                    raise GARLException(str(exc), 409) from exc
                run = (await self.durable_execution_service.prepare_resume(execution_id)).run
                return self._durable_response(response, run)
            return self._durable_response(
                "An action is waiting for approval.",
                decision.run,
                decision.pending_approval.approval_id,
            )

        if decision.status is ExecutionRunStatus.RECOVERY_REQUIRED:
            return self._durable_response("Execution requires recovery before it can continue.", decision.run)
        if decision.may_execute:
            state = CognitiveState(
                objective=decision.run.objective,
                execution=decision.execution_state,
            )
            response = await self.pipeline.run_persisted_step(
                execution_id=execution_id,
                step_id=decision.next_step_id,
                messages=self._persisted_messages(decision.run),
                state=state,
                finalize=False,
            )
            latest = await self.durable_execution_service.prepare_resume(execution_id)
            evaluation_context = await self.durable_execution_service.objective_evaluation_context(
                execution_id
            )
            evaluation = self.pipeline.evaluate_execution_objective(
                latest.run.objective,
                latest.execution_state,
                evaluation_context,
            )
            if evaluation is not None and not latest.may_execute:
                if evaluation.complete:
                    await self.durable_execution_service.complete_if_finished(execution_id)
                    latest = await self.durable_execution_service.prepare_resume(execution_id)
                else:
                    await self.durable_execution_service.fail_if_finished(execution_id)
                    latest = await self.durable_execution_service.prepare_resume(execution_id)
                    response = ChatResponse(
                        response=(
                            "Objective incomplete: "
                            + "; ".join(evaluation.gaps)
                        )
                    )
            return self._durable_response(
                response.response,
                latest.run,
                latest.pending_approval.approval_id if latest.pending_approval else None,
            )
        return self._durable_response("Execution has no legal pending step.", decision.run)

    @staticmethod
    def _persisted_messages(run) -> list[ConversationMessage]:
        return [
            ConversationMessage(role=item["role"], content=item["content"])
            for item in run.execution_context.get("messages", [])
        ]

    @staticmethod
    def _durable_response(
        response: str,
        run,
        pending_approval_id: str | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            response=response,
            execution_id=run.execution_id,
            execution_status=run.status.value,
            pending_approval_id=pending_approval_id,
        )
    # ======================================================
    # STATE
    # ======================================================

    def _save_state(
        self,
        conversation_id: str,
        state,
    ) -> None:

        self.state_repository.save(
            conversation_id,
            state,
        )

        logger.info(
            "Saved cognitive state: %s",
            conversation_id,
        )
    # ======================================================
    # KNOWLEDGE
    # ======================================================

    async def ingest_document(
        self,
        path: str,
    ) -> int:

        logger.info(
            "Ingesting document: %s",
            path,
        )

        return (
            await self.knowledge_service
            .ingest_document(path)
        )
    async def ingest_directory(
        self,
        directory: str,
    ) -> int:

        logger.info(
            "Ingesting directory: %s",
            directory,
        )

        return (
            await self.knowledge_service
            .ingest_directory(
                directory
            )
        )
    async def search_knowledge(
        self,
        query: str,
        limit: int = 5,
    ):

        return (
            await self.knowledge_service
            .search(
                query,
                limit,
            )
        )
    async def search_context(
        self,
        query: str,
        limit: int = 5,
    ) -> str:

        return (
            await self.knowledge_service
            .search_context(
                query,
                limit,
            )
        )
    # ======================================================
    # MEMORY
    # ======================================================

    async def clear_memory(
        self,
        conversation_id: str,
    ) -> None:

        logger.info(
            "Clearing memory: %s",
            conversation_id,
        )

        await self.memory_service.clear(
            conversation_id
        )
    # ======================================================
    # STATE ACCESS
    # ======================================================

    def get_state(
        self,
        conversation_id: str,
    ):

        return (
            self.state_repository
            .get_or_create(
                conversation_id
            )
        )
    def reset_conversation(
        self,
        conversation_id: str,
    ) -> None:

        self.state_repository.delete(
            conversation_id
        )

        logger.info(
            "Conversation reset: %s",
            conversation_id,
        )
    # ======================================================
    # HEALTH
    # ======================================================

    async def health_check(
        self,
    ) -> dict:

        return {
            "knowledge": (
                await self.knowledge_service
                .health_check()
            ),
            "indexed_chunks": (
                await self.knowledge_service
                .indexed_chunks()
            ),
        }
    def __repr__(
        self,
    ) -> str:

        return (
            "AgentService("
            f"pipeline={self.pipeline.__class__.__name__}, "
            f"memory={self.memory_service.__class__.__name__}, "
            f"knowledge={self.knowledge_service.__class__.__name__})"
        )
