from pathlib import Path

from src.core.prompts import SystemPrompts

from src.models.artifact import (
    Artifact,
    ArtifactType,
)

from src.models.conversation import (
    ConversationMessage,
)

from src.models.execution_state import (
    ExecutionState,
    StepResult,
)

from src.models.plan import (
    ExecutionPlan,
    PlanStep,
)

from src.models.tool_risk import (
    PermissionDecision,
)

from src.services.context_builder import (
    ContextBuilder,
)

from src.services.llm_service import (
    LLMService,
)

from src.services.permission_service import (
    PermissionService,
)

from src.services.variable_resolver import (
    VariableResolver,
)

from src.tools.tool_manager import (
    ToolManager,
)

from src.utils.logger import (
    logger,
)


class ExecutorService:

    def __init__(
        self,
        llm: LLMService,
        context_builder: ContextBuilder,
        tool_manager: ToolManager,
        variable_resolver: VariableResolver,
        permission_service: PermissionService,
    ):
        self.llm = llm
        self.context_builder = context_builder
        self.tool_manager = tool_manager
        self.variable_resolver = variable_resolver
        self.permission_service = permission_service

    async def execute(
        self,
        messages: list[ConversationMessage],
        plan: ExecutionPlan,
        state: ExecutionState,
    ) -> str:

        for step in plan.steps:

            state.current_step = step.id

            logger.info(
                "Executing step %s: %s",
                step.id,
                step.action,
            )

            resolved_input = (
                self.variable_resolver.resolve(
                    step.input,
                    state,
                )
            )

            resolved_arguments = (
                self.variable_resolver.resolve(
                    step.arguments,
                    state,
                )
            )

            if step.tool:

                result = await self._execute_tool_step(
                    step,
                    resolved_arguments,
                    state,
                )

            else:

                result = await self._execute_llm_step(
                    step,
                    resolved_input,
                    messages,
                )

            state.record(result)

            if not result.success:

                return (
                    result.error
                    or "Execution failed."
                )

            state.variables[
                f"step{step.id}"
            ] = result.output
            logger.info(
                "Stored variable step%s = %s",
                step.id,
                state.variables[f"step{step.id}"],
            )

        last = state.last_result()

        if last is None:
            return "Execution completed."

        return str(last.output)

    async def _execute_tool_step(
        self,
        step: PlanStep,
        arguments: dict,
        state: ExecutionState,
    ) -> StepResult:

        tool = self.tool_manager.get(
            step.tool
        )

        if tool is None:

            return StepResult(
                step_id=step.id,
                success=False,
                error=f"Tool '{step.tool}' not found.",
                tool=step.tool,
                action=step.action,
            )

        if not arguments:

            arguments = {
                "query": step.input
            }

        valid, error = (
            self.tool_manager.validate_arguments(
                step.tool,
                arguments,
            )
        )

        if not valid:

            return StepResult(
                step_id=step.id,
                success=False,
                error=error,
                tool=step.tool,
                action=step.action,
            )

        permission = (
            self.permission_service.evaluate(
                tool_name=step.tool,
                arguments=arguments,
            )
        )

        logger.info(
            "Permission %s -> %s",
            permission.risk.value,
            permission.decision.value,
        )

        if (
            permission.decision
            == PermissionDecision.DENY
        ):

            return StepResult(
                step_id=step.id,
                success=False,
                error=permission.reason,
                tool=step.tool,
                action=step.action,
                metadata={
                    "permission_decision": (
                        permission.decision.value
                    ),
                },
            )

        if (
            permission.decision
            == PermissionDecision.REQUIRE_APPROVAL
        ):

            state.require_approval(
                step_id=step.id,
                tool_name=step.tool,
                arguments=arguments,
                reason=permission.reason,
                risk_level=permission.risk.value,
            )

            return StepResult(
                step_id=step.id,
                success=False,
                error=f"Approval required: {permission.reason}",
                tool=step.tool,
                action=step.action,
            )

        try:

            tool_result = await tool.execute(
                **arguments
            )
            logger.info(
                "Tool output: %s",
                tool_result.output,
            )

        except Exception as exc:

            return StepResult(
                step_id=step.id,
                success=False,
                error=str(exc),
                tool=step.tool,
                action=step.action,
            )

        # ------------------------------------
        # ADD THIS LINE
        # ------------------------------------

        artifact = None

        if (
            step.tool == "filesystem"
            and arguments.get("action") == "write_file"
        ):

            path = arguments.get(
                "path",
                "",
            )

            content = arguments.get(
                "content",
                "",
            )

            artifact = Artifact(
                id=f"step-{step.id}",
                name=Path(path).name,
                artifact_type=self._artifact_type(
                    path
                ),
                path=path,
                preview=content,
                metadata={
                    "tool": step.tool,
                },
            )

        return StepResult(
            step_id=step.id,
            success=tool_result.success,
            output=tool_result.output,
            error=(
                None
                if tool_result.success
                else (
                    tool_result.metadata.get(
                        "error",
                        "Tool execution failed.",
                    )
                    if tool_result.metadata
                    else "Tool execution failed."
                )
            ),
            tool=step.tool,
            action=step.action,
            artifact=artifact,
            metadata=tool_result.metadata or {},
        )

    async def _execute_llm_step(
        self,
        step: PlanStep,
        resolved_input: str,
        messages: list[ConversationMessage],
    ) -> StepResult:

        logger.info(
            "Executing LLM step %s",
            step.id,
        )

        chat_messages = (
            await self.context_builder.build(
                SystemPrompts.DEFAULT_ASSISTANT,
                messages,
            )
        )

        chat_messages.append(
            {
                "role": "user",
                "content": resolved_input,
            }
        )

        try:

            response = await self.llm.generate(
                chat_messages
            )

        except Exception as exc:

            return StepResult(
                step_id=step.id,
                success=False,
                error=str(exc),
                tool="llm",
                action=step.action,
            )

        artifact = None

        if (
            "```python" in response
            or step.action.lower().startswith(
                "create"
            )
        ):

            artifact = Artifact(
                id=f"step-{step.id}",
                name="generated.py",
                artifact_type=ArtifactType.PYTHON,
                path="",
                preview=response,
                metadata={
                    "generated": True,
                },
            )

        return StepResult(
            step_id=step.id,
            success=True,
            output=response,
            tool="llm",
            action=step.action,
            artifact=artifact,
        )

    def _artifact_type(
        self,
        filename: str,
    ) -> ArtifactType:

        suffix = (
            Path(filename)
            .suffix
            .lower()
        )

        mapping = {
            ".py": ArtifactType.PYTHON,
            ".txt": ArtifactType.TEXT,
            ".md": ArtifactType.MARKDOWN,
            ".json": ArtifactType.JSON,
            ".csv": ArtifactType.CSV,
            ".pdf": ArtifactType.PDF,
            ".png": ArtifactType.IMAGE,
            ".jpg": ArtifactType.IMAGE,
            ".jpeg": ArtifactType.IMAGE,
            ".webp": ArtifactType.IMAGE,
        }

        return mapping.get(
            suffix,
            ArtifactType.UNKNOWN,
        )
