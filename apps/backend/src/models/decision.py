from dataclasses import dataclass
from enum import Enum


class DecisionType(Enum):

    RETURN = "return"

    RETRY = "retry"

    REPLAN = "replan"

    WAIT_FOR_APPROVAL = "wait_for_approval"


@dataclass
class Decision:

    action: DecisionType

    reason: str