from dataclasses import dataclass, field
from typing import Any

from src.models.artifact import Artifact


# ==========================================================
# STEP RESULT
# ==========================================================

@dataclass
class StepResult:

    step_id: int

    success: bool

    output: Any = None

    error: str | None = None

    tool: str | None = None

    action: str | None = None

    artifact: Artifact | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ==========================================================
# APPROVAL RECORD
# ==========================================================

@dataclass
class ApprovalRecord:

    step_id: int

    tool_name: str

    arguments: dict[str, Any]

    reason: str

    risk_level: str

    decision: str

    result: str | None = None


# ==========================================================
# EXECUTION STATE
# ==========================================================

@dataclass
class ExecutionState:

    current_step: int = 0

    attempt: int = 0

    variables: dict[str, Any] = field(
        default_factory=dict
    )

    history: list[StepResult] = field(
        default_factory=list
    )

    approval_required: bool = False

    pending_tool: str | None = None

    pending_arguments: dict[str, Any] | None = None

    approval_reason: str | None = None

    risk_level: str | None = None

    pending_step_id: int | None = None

    approval_history: list[
        ApprovalRecord
    ] = field(
        default_factory=list
    )

    # ======================================================
    # EXECUTION
    # ======================================================

    def begin_attempt(
        self,
    ) -> None:

        self.attempt += 1

        self.current_step = 0

        self.variables.clear()

    def record(
        self,
        result: StepResult,
    ) -> None:

        self.history.append(
            result
        )

    def last_result(
        self,
    ) -> StepResult | None:

        if not self.history:
            return None

        return self.history[-1]

    def last_artifact(
        self,
    ) -> Artifact | None:

        for result in reversed(
            self.history
        ):

            if result.artifact:

                return result.artifact

        return None
        # ======================================================
    # APPROVAL
    # ======================================================

    def require_approval(
        self,
        *,
        step_id: int,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str,
        risk_level: str,
    ) -> None:

        self.approval_required = True

        self.pending_step_id = step_id

        self.pending_tool = tool_name

        self.pending_arguments = dict(
            arguments
        )

        self.approval_reason = reason

        self.risk_level = risk_level

    def record_approval(
        self,
        *,
        decision: str,
        result: str | None = None,
    ) -> None:

        if (
            self.pending_step_id is None
            or self.pending_tool is None
            or self.pending_arguments is None
            or self.approval_reason is None
            or self.risk_level is None
        ):
            return

        self.approval_history.append(
            ApprovalRecord(
                step_id=self.pending_step_id,
                tool_name=self.pending_tool,
                arguments=dict(
                    self.pending_arguments
                ),
                reason=self.approval_reason,
                risk_level=self.risk_level,
                decision=decision,
                result=result,
            )
        )

    def clear_approval(
        self,
    ) -> None:

        self.approval_required = False

        self.pending_step_id = None

        self.pending_tool = None

        self.pending_arguments = None

        self.approval_reason = None

        self.risk_level = None

    # ======================================================
    # UTILITIES
    # ======================================================

    def clear_history(
        self,
    ) -> None:

        self.history.clear()

    def reset(
        self,
    ) -> None:

        self.current_step = 0

        self.attempt = 0

        self.variables.clear()

        self.history.clear()

        self.clear_approval()

        self.approval_history.clear()