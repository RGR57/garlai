from dataclasses import dataclass
from enum import Enum


class ExecutionClassification(str, Enum):
    READ_ONLY = "read_only"
    CONSEQUENTIAL = "consequential"


@dataclass(frozen=True)
class ExecutionPolicy:
    classification: ExecutionClassification
    retry_known_failure: bool
    supports_idempotency_key: bool = False

    @property
    def is_consequential(self) -> bool:
        return self.classification is ExecutionClassification.CONSEQUENTIAL


READ_ONLY_POLICY = ExecutionPolicy(
    classification=ExecutionClassification.READ_ONLY,
    retry_known_failure=True,
)

CONSERVATIVE_POLICY = ExecutionPolicy(
    classification=ExecutionClassification.CONSEQUENTIAL,
    retry_known_failure=False,
)
