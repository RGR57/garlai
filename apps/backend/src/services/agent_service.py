from src.models.chat_response import (
    ChatResponse,
)

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
    # ======================================================
    # PUBLIC ENTRYPOINT
    # ======================================================

    async def respond(
        self,
        conversation_id: str,
        messages: list[ConversationMessage],
    ) -> ChatResponse:

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