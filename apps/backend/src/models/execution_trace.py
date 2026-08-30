from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ExecutionEventType(str, Enum):

    # ======================================================
    # REASONING
    # ======================================================

    REASONING = "reasoning"

    OBJECTIVE = "objective"

    CONSTRAINT = "constraint"

    ASSUMPTION = "assumption"

    STRATEGY = "strategy"

    # ======================================================
    # PLANNING
    # ======================================================

    PLAN_CREATED = "plan_created"

    # ======================================================
    # EXECUTION
    # ======================================================

    STEP_STARTED = "step_started"

    STEP_COMPLETED = "step_completed"

    TOOL_CALLED = "tool_called"

    TOOL_RESULT = "tool_result"

    # ======================================================
    # REVIEW
    # ======================================================

    REVIEW = "review"

    # ======================================================
    # DECISION
    # ======================================================

    DECISION = "decision"

    RETRY = "retry"

    REPLAN = "replan"

    # ======================================================
    # APPROVAL
    # ======================================================

    APPROVAL_REQUIRED = "approval_required"

    APPROVAL_GRANTED = "approval_granted"

    APPROVAL_REJECTED = "approval_rejected"

    # ======================================================
    # FINAL
    # ======================================================

    FINAL_RESULT = "final_result"

    ERROR = "error"


@dataclass
class ExecutionEvent:

    timestamp: datetime

    event_type: ExecutionEventType

    message: str

    confidence: float = 1.0

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class ExecutionTrace:

    events: list[ExecutionEvent] = field(
        default_factory=list
    )

    def add(
        self,
        *,
        event_type: ExecutionEventType,
        message: str,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:

        self.events.append(
            ExecutionEvent(
                timestamp=datetime.now(
                    timezone.utc
                ),
                event_type=event_type,
                message=message,
                confidence=confidence,
                metadata=metadata or {},
            )
        )

    def last_event(
        self,
    ) -> ExecutionEvent | None:

        if not self.events:
            return None

        return self.events[-1]

    def clear(
        self,
    ) -> None:

        self.events.clear()