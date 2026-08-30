from enum import Enum


class RiskLevel(str, Enum):
    """
    Risk classification for actions GARL may execute.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionDecision(str, Enum):
    """
    Decision produced by the permission engine.
    """

    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"