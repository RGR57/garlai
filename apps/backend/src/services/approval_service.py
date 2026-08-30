from src.models.execution_state import (
    ExecutionState,
    StepResult,
)
from src.tools.tool_manager import ToolManager
from src.utils.logger import logger


class ApprovalService:

    def __init__(
        self,
        tool_manager: ToolManager,
    ):
        self.tool_manager = tool_manager

    async def approve(
        self,
        state: ExecutionState,
    ) -> str:

        # ======================================================
        # VERIFY PENDING APPROVAL
        # ======================================================

        if not state.approval_required:
            return "There is no pending action requiring approval."

        tool_name = state.pending_tool
        arguments = state.pending_arguments
        step_id = state.pending_step_id

        if (
            tool_name is None
            or arguments is None
            or step_id is None
        ):
            logger.error(
                "Approval state is incomplete."
            )

            state.clear_approval()

            return (
                "The pending approval could not be resumed "
                "because its execution state was incomplete."
            )

        logger.info(
            f"User approved pending action: "
            f"tool={tool_name}, "
            f"arguments={arguments}"
        )

        # ======================================================
        # GET TOOL
        # ======================================================

        tool = self.tool_manager.get(
            tool_name
        )

        if tool is None:

            error = (
                f"Approved tool '{tool_name}' "
                "is no longer available."
            )

            logger.error(error)

            state.record_approval(
                decision="approved",
                result=error,
            )

            state.clear_approval()

            return error

        # ======================================================
        # REVALIDATE ARGUMENTS
        # ======================================================

        is_valid, validation_error = (
            self.tool_manager.validate_arguments(
                tool_name,
                arguments,
            )
        )

        if not is_valid:

            error = (
                validation_error
                or "Approved tool arguments are invalid."
            )

            logger.error(
                f"Approved action validation failed: "
                f"{error}"
            )

            state.record_approval(
                decision="approved",
                result=error,
            )

            state.clear_approval()

            return error

        # ======================================================
        # EXECUTE EXACT STORED ACTION
        # ======================================================

        try:

            tool_result = await tool.execute(
                **arguments
            )

        except Exception as exc:

            error = (
                f"Approved tool '{tool_name}' "
                f"execution failed: "
                f"{type(exc).__name__}: "
                f"{str(exc)}"
            )

            logger.exception(error)

            state.record(
                StepResult(
                    step_id=step_id,
                    success=False,
                    error=error,
                    tool=tool_name,
                )
            )

            state.record_approval(
                decision="approved",
                result=error,
            )

            state.clear_approval()

            return error

        logger.info(
            f"Approved tool result: "
            f"tool={tool_result.tool_name}, "
            f"success={tool_result.success}, "
            f"output={tool_result.output}, "
            f"metadata={tool_result.metadata}"
        )

        # ======================================================
        # TOOL FAILURE
        # ======================================================

        if not tool_result.success:

            error = None

            if tool_result.metadata:
                error = tool_result.metadata.get(
                    "error"
                )

            error = (
                error
                or "Approved tool execution failed."
            )

            state.record(
                StepResult(
                    step_id=step_id,
                    success=False,
                    output=tool_result.output,
                    error=error,
                    tool=tool_name,
                )
            )

            state.record_approval(
                decision="approved",
                result=error,
            )

            state.clear_approval()

            return error

        # ======================================================
        # SUCCESS
        # ======================================================

        state.record(
            StepResult(
                step_id=step_id,
                success=True,
                output=tool_result.output,
                tool=tool_name,
            )
        )

        state.variables[
            f"step{step_id}"
        ] = tool_result.output

        state.record_approval(
            decision="approved",
            result=str(tool_result.output),
        )

        state.clear_approval()

        logger.info(
            "Approved pending action executed successfully."
        )

        return str(
            tool_result.output
        )

    async def reject(
        self,
        state: ExecutionState,
    ) -> str:

        if not state.approval_required:
            return "There is no pending action requiring approval."

        tool_name = state.pending_tool
        arguments = state.pending_arguments

        logger.info(
            f"User rejected pending action: "
            f"tool={tool_name}, "
            f"arguments={arguments}"
        )

        state.record_approval(
            decision="rejected",
            result="User rejected the pending action.",
        )

        state.clear_approval()

        return "Pending action rejected. Nothing was executed."
