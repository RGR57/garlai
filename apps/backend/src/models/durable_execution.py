from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TypeAlias


JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


class DurableStateCorruptionError(ValueError):
    """Persisted durable state could not be safely reconstructed."""


class ApprovalPayloadMismatchError(ValueError):
    """An approval was presented for a different frozen operation payload."""


class ApprovalIdentityMismatchError(ValueError):
    """An approval was presented for a different durable execution."""


class ExecutionRunStatus(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    RECOVERY_REQUIRED = "recovery_required"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED}


class DurableStepStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    KNOWN_FAILED = "known_failed"
    WAITING_APPROVAL = "waiting_approval"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"

    @property
    def is_terminal(self) -> bool:
        return self in {
            self.COMPLETED,
            self.REJECTED,
        }


class OperationEventType(str, Enum):
    INTENT_RECORDED = "intent_recorded"
    COMPLETED = "completed"
    KNOWN_FAILED = "known_failed"
    UNCERTAIN = "uncertain"


class ApprovalEventType(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"


RUN_STATE_TRANSITIONS: dict[ExecutionRunStatus, frozenset[ExecutionRunStatus]] = {
    ExecutionRunStatus.PLANNING: frozenset(
        {ExecutionRunStatus.RUNNING, ExecutionRunStatus.FAILED}
    ),
    ExecutionRunStatus.RUNNING: frozenset(
        {
            ExecutionRunStatus.WAITING_APPROVAL,
            ExecutionRunStatus.RECOVERY_REQUIRED,
            ExecutionRunStatus.COMPLETED,
            ExecutionRunStatus.FAILED,
        }
    ),
    ExecutionRunStatus.WAITING_APPROVAL: frozenset(
        {ExecutionRunStatus.RUNNING, ExecutionRunStatus.FAILED}
    ),
    ExecutionRunStatus.RECOVERY_REQUIRED: frozenset(
        {ExecutionRunStatus.RUNNING}
    ),
    ExecutionRunStatus.COMPLETED: frozenset(),
    ExecutionRunStatus.FAILED: frozenset(),
}


STEP_STATE_TRANSITIONS: dict[DurableStepStatus, frozenset[DurableStepStatus]] = {
    DurableStepStatus.PENDING: frozenset(
        {
            DurableStepStatus.EXECUTING,
            DurableStepStatus.WAITING_APPROVAL,
        }
    ),
    DurableStepStatus.EXECUTING: frozenset(
        {
            DurableStepStatus.COMPLETED,
            DurableStepStatus.KNOWN_FAILED,
            DurableStepStatus.UNCERTAIN,
        }
    ),
    DurableStepStatus.WAITING_APPROVAL: frozenset(
        {
            DurableStepStatus.PENDING,
            DurableStepStatus.EXECUTING,
            DurableStepStatus.REJECTED,
            DurableStepStatus.KNOWN_FAILED,
        }
    ),
    DurableStepStatus.KNOWN_FAILED: frozenset(
        {DurableStepStatus.PENDING, DurableStepStatus.EXECUTING}
    ),
    DurableStepStatus.COMPLETED: frozenset(),
    DurableStepStatus.REJECTED: frozenset(),
    DurableStepStatus.UNCERTAIN: frozenset(),
}


def can_transition_run(
    current: ExecutionRunStatus,
    target: ExecutionRunStatus,
) -> bool:
    return target in RUN_STATE_TRANSITIONS[current]


def can_transition_step(
    current: DurableStepStatus,
    target: DurableStepStatus,
) -> bool:
    return target in STEP_STATE_TRANSITIONS[current]


def canonical_payload_hash(
    tool: str,
    action: str,
    arguments: dict[str, Any],
) -> str:
    """Hash the exact tool payload without depending on mapping insertion order."""
    payload = {
        "tool": tool,
        "action": action,
        "arguments": _validated_json_mapping(arguments, "arguments"),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validated_json_value(value: Any, field_name: str) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be valid JSON") from exc
        return value

    if isinstance(value, list):
        return [
            _validated_json_value(item, f"{field_name}[]")
            for item in value
        ]

    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {
            key: _validated_json_value(item, f"{field_name}.{key}")
            for key, item in value.items()
        }

    raise ValueError(f"{field_name} must contain only JSON values")


def _validated_json_mapping(value: Any, field_name: str) -> dict[str, JsonValue]:
    validated = _validated_json_value(value, field_name)
    if not isinstance(validated, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return validated


@dataclass(frozen=True)
class OperationClaim:
    granted: bool
    execution_id: str
    step_id: int
    operation_id: str
    attempt_id: str | None = None

    @classmethod
    def denied(
        cls,
        execution_id: str,
        step_id: int,
        operation_id: str,
    ) -> "OperationClaim":
        return cls(False, execution_id, step_id, operation_id)


@dataclass(frozen=True)
class OrphanedOperation:
    """A committed consequential intent with no durable terminal fact."""

    execution_id: str
    step_id: int
    operation_id: str


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    execution_id: str
    step_id: int
    operation_id: str
    tool: str
    action: str
    arguments: dict[str, JsonValue]
    reason: str
    risk_level: str
    payload_hash: str
    event_type: ApprovalEventType = ApprovalEventType.REQUESTED
    requested_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "arguments",
            _validated_json_mapping(self.arguments, "arguments"),
        )
        if canonical_payload_hash(
            self.tool,
            self.action,
            self.arguments,
        ) != self.payload_hash:
            raise ApprovalPayloadMismatchError(
                "Approval payload hash does not match its frozen operation."
            )

    @classmethod
    def create(
        cls,
        *,
        approval_id: str,
        execution_id: str,
        step_id: int,
        operation_id: str,
        tool: str,
        action: str,
        arguments: dict[str, Any],
        reason: str,
        risk_level: str,
        requested_at: datetime | None = None,
    ) -> "ApprovalRequest":
        validated_arguments = _validated_json_mapping(arguments, "arguments")
        return cls(
            approval_id=approval_id,
            execution_id=execution_id,
            step_id=step_id,
            operation_id=operation_id,
            tool=tool,
            action=action,
            arguments=validated_arguments,
            reason=reason,
            risk_level=risk_level,
            payload_hash=canonical_payload_hash(tool, action, validated_arguments),
            requested_at=requested_at,
        )

    def assert_authorizes(
        self,
        *,
        execution_id: str,
        payload_hash: str,
    ) -> None:
        if execution_id != self.execution_id:
            raise ApprovalIdentityMismatchError(
                "Approval does not belong to this execution."
            )
        current_payload_hash = canonical_payload_hash(
            self.tool,
            self.action,
            self.arguments,
        )
        if (
            payload_hash != self.payload_hash
            or current_payload_hash != self.payload_hash
        ):
            raise ApprovalPayloadMismatchError(
                "Approval does not authorize this operation payload."
            )


@dataclass
class DurableStep:
    step_id: int
    ordinal: int
    action: str
    tool: str | None
    plan_input: str = ""
    arguments: dict[str, JsonValue] = field(default_factory=dict)
    resolved_arguments: dict[str, JsonValue] | None = None
    classification: str | None = None
    status: DurableStepStatus = DurableStepStatus.PENDING
    operation_id: str | None = None
    payload_hash: str | None = None
    attempt_count: int = 0
    result: dict[str, JsonValue] | None = None
    error: dict[str, JsonValue] | None = None
    artifact: dict[str, JsonValue] | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.arguments = _validated_json_mapping(self.arguments, "arguments")
        if self.resolved_arguments is not None:
            self.resolved_arguments = _validated_json_mapping(
                self.resolved_arguments,
                "resolved_arguments",
            )
        for field_name in ("result", "error", "artifact"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(self, field_name, _validated_json_mapping(value, field_name))
        self.metadata = _validated_json_mapping(self.metadata, "metadata")


@dataclass
class ExecutionRun:
    execution_id: str
    objective: str
    conversation_id: str | None = None
    status: ExecutionRunStatus = ExecutionRunStatus.PLANNING
    plan_version: int = 1
    current_step_id: int | None = None
    next_step_id: int | None = None
    attempt_count: int = 0
    iteration_count: int = 0
    final_response: str | None = None
    execution_context: dict[str, JsonValue] = field(default_factory=dict)
    variables: dict[str, JsonValue] = field(default_factory=dict)
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    steps: list[DurableStep] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.execution_context = _validated_json_mapping(
            self.execution_context,
            "execution_context",
        )
        self.variables = _validated_json_mapping(self.variables, "variables")
        self.metadata = _validated_json_mapping(self.metadata, "metadata")
        if not all(isinstance(step, DurableStep) for step in self.steps):
            raise ValueError("steps must contain DurableStep values")
