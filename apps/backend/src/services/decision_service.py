from src.models.decision import (
    Decision,
    DecisionType,
)
from src.models.execution_state import ExecutionState


class DecisionService:

    async def decide(
        self,
        state: ExecutionState,
    ) -> Decision:

        # ======================================================
        # APPROVAL
        # ======================================================

        if state.approval_required:

            return Decision(
                action=DecisionType.WAIT_FOR_APPROVAL,
                reason=(
                    state.approval_reason
                    or "User approval is required."
                ),
            )

        # ======================================================
        # LAST EXECUTION RESULT
        # ======================================================

        last = state.last_result()

        if last is None:

            return Decision(
                action=DecisionType.REPLAN,
                reason=(
                    "Execution produced no result. "
                    "A new plan is required."
                ),
            )

        # ======================================================
        # SUCCESS
        # ======================================================

        if last.success:

            return Decision(
                action=DecisionType.RETURN,
                reason="Execution completed successfully.",
            )

        error = (
            last.error
            or "Unknown execution failure."
        )

        normalized_error = error.lower()

        # ======================================================
        # REPLAN CONDITIONS
        # ======================================================

        replan_signals = (
            "not available",
            "not registered",
            "unknown argument",
            "requires argument",
            "invalid argument",
            "unsupported",
            "not found",
            "no such file",
            "cannot find",
        )

        if any(
            signal in normalized_error
            for signal in replan_signals
        ):

            return Decision(
                action=DecisionType.REPLAN,
                reason=(
                    "The current execution plan cannot "
                    f"continue safely: {error}"
                ),
            )

        # ======================================================
        # RETRY CONDITIONS
        # ======================================================

        retry_signals = (
            "timeout",
            "timed out",
            "temporarily unavailable",
            "connection reset",
            "connection error",
            "rate limit",
            "429",
            "503",
        )

        if any(
            signal in normalized_error
            for signal in retry_signals
        ):

            return Decision(
                action=DecisionType.RETRY,
                reason=(
                    "The failure may be transient: "
                    f"{error}"
                ),
            )

        # ======================================================
        # UNKNOWN / DETERMINISTIC FAILURE
        # ======================================================

        return Decision(
            action=DecisionType.REPLAN,
            reason=(
                "Execution failed and repeating the same "
                "plan is unlikely to help. "
                f"Failure: {error}"
            ),
        )