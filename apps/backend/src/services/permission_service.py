from dataclasses import dataclass, field
from typing import Any

from src.models.tool_risk import (
    PermissionDecision,
    RiskLevel,
)
from src.services.execution_policy import (
    CONSERVATIVE_POLICY,
    READ_ONLY_POLICY,
    ExecutionPolicy,
)


@dataclass
class PermissionResult:
    decision: PermissionDecision
    risk: RiskLevel
    reason: str
    execution_policy: ExecutionPolicy = field(
        default_factory=lambda: CONSERVATIVE_POLICY
    )


class PermissionService:
    """
    Central authorization layer for GARL tool execution.

    The planner may REQUEST an action.
    This service decides whether GARL is permitted
    to actually execute it.
    """

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> PermissionResult:

        if tool_name == "filesystem":
            result = self._evaluate_filesystem(arguments)
        elif tool_name == "terminal":
            result = self._evaluate_terminal(arguments)
        elif tool_name == "git":
            result = self._evaluate_git(arguments)
        elif tool_name == "calculator":
            result = self._allow(
                RiskLevel.LOW,
                "Calculator operations are non-mutating.",
            )
        elif tool_name == "web_search":
            result = self._allow(
                RiskLevel.LOW,
                "Public web search is read-only.",
            )
        elif tool_name in {"browser_navigate", "browser_observe"}:
            result = self._allow(
                RiskLevel.LOW,
                "Browser navigation and observation are read-oriented under navigation policy.",
            )
        elif tool_name in {"browser_select", "browser_fill"}:
            result = self._allow(
                RiskLevel.MEDIUM,
                "Browser preparation is allowed but treated as a consequential action.",
            )
        elif tool_name == "browser_submit":
            result = self._require_approval(
                RiskLevel.HIGH,
                "Browser submit commits external state and requires approval.",
            )
        else:
            # Unknown tools must never silently execute.
            result = self._deny(
                RiskLevel.CRITICAL,
                (
                    f"No permission policy exists for "
                    f"tool '{tool_name}'."
                ),
            )
        result.execution_policy = self._execution_policy(tool_name, arguments)
        return result

    def _execution_policy(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ExecutionPolicy:
        if tool_name in {"calculator", "web_search", "browser_navigate", "browser_observe"}:
            return READ_ONLY_POLICY
        if tool_name == "filesystem" and arguments.get("action") in {
            "read_file",
            "list_directory",
            "exists",
            "metadata",
        }:
            return READ_ONLY_POLICY
        if tool_name == "git" and str(arguments.get("action", "")).lower() in {
            "branch",
            "status",
            "log",
            "diff",
        }:
            return READ_ONLY_POLICY

        # Terminal and unclassified actions retain the conservative default.
        return CONSERVATIVE_POLICY

    # ==========================================================
    # FILESYSTEM
    # ==========================================================

    def _evaluate_filesystem(
        self,
        arguments: dict[str, Any],
    ) -> PermissionResult:

        action = arguments.get("action")

        if action in {
            "read_file",
            "list_directory",
            "exists",
            "metadata",
        }:
            return self._allow(
                RiskLevel.LOW,
                f"Filesystem action '{action}' is read-only.",
            )

        if action == "create_directory":
            return self._allow(
                RiskLevel.MEDIUM,
                "Creating a workspace directory is allowed.",
            )

        if action == "append_file":
            return self._allow(
                RiskLevel.MEDIUM,
                "Appending to a workspace file is a controlled mutation.",
            )

        if action == "write_file":

            path = str(
                arguments.get(
                    "path",
                    "",
                )
            ).lower()

            # Source-code writes deserve stronger protection.
            protected_prefixes = (
                "src/",
                "src\\",
                "tests/",
                "tests\\",
            )

            if path.startswith(
                protected_prefixes
            ):
                return self._require_approval(
                    RiskLevel.HIGH,
                    (
                        "Writing directly to source or test "
                        "code requires approval."
                    ),
                )

            return self._allow(
                RiskLevel.MEDIUM,
                "Workspace file write is allowed.",
            )

        return self._deny(
            RiskLevel.CRITICAL,
            (
                "Filesystem action is unknown or "
                f"not permitted: {action}"
            ),
        )

    # ==========================================================
    # TERMINAL
    # ==========================================================

    def _evaluate_terminal(
        self,
        arguments: dict[str, Any],
    ) -> PermissionResult:

        command = str(
            arguments.get(
                "query",
                arguments.get(
                    "command",
                    "",
                ),
            )
        ).strip()

        command_lower = command.lower()

        if not command:
            return self._deny(
                RiskLevel.CRITICAL,
                "Empty terminal command.",
            )

        # ----------------------------------------------
        # CRITICAL / DESTRUCTIVE PATTERNS
        # ----------------------------------------------

        critical_patterns = (
            "rm -rf",
            "del /f",
            "del /s",
            "rmdir /s",
            "rd /s",
            "format ",
            "diskpart",
            "shutdown",
            "restart-computer",
            "stop-computer",
        )

        if any(
            pattern in command_lower
            for pattern in critical_patterns
        ):
            return self._deny(
                RiskLevel.CRITICAL,
                (
                    "Potentially destructive terminal "
                    "command blocked."
                ),
            )

        # ----------------------------------------------
        # HIGH-RISK MUTATIONS
        # ----------------------------------------------

        high_risk_patterns = (
            "pip install",
            "pip uninstall",
            "npm install",
            "npm uninstall",
            "npm remove",
            "git push",
            "git reset",
            "git clean",
        )

        if any(
            pattern in command_lower
            for pattern in high_risk_patterns
        ):
            return self._require_approval(
                RiskLevel.HIGH,
                (
                    "Terminal command may modify the "
                    "environment or external state."
                ),
            )

        # Terminal itself has broad capabilities.
        return self._allow(
            RiskLevel.MEDIUM,
            "Terminal command passed current safety policy.",
        )

    # ==========================================================
    # GIT
    # ==========================================================

    def _evaluate_git(
        self,
        arguments: dict[str, Any],
    ) -> PermissionResult:

        action = str(
            arguments.get(
                "action",
                "",
            )
        ).lower()

        if action in {
            "branch",
            "status",
            "log",
            "diff",
        }:
            return self._allow(
                RiskLevel.LOW,
                f"Git action '{action}' is read-only.",
            )

        if action in {
            "add",
            "commit",
        }:
            return self._require_approval(
                RiskLevel.MEDIUM,
                (
                    f"Git action '{action}' modifies "
                    "repository state."
                ),
            )

        if action in {
            "push",
            "reset",
            "clean",
            "checkout",
        }:
            return self._require_approval(
                RiskLevel.HIGH,
                (
                    f"Git action '{action}' can significantly "
                    "change local or remote repository state."
                ),
            )

        return self._deny(
            RiskLevel.CRITICAL,
            (
                "Git action is unknown or "
                f"not permitted: {action}"
            ),
        )

    # ==========================================================
    # RESULT HELPERS
    # ==========================================================

    def _allow(
        self,
        risk: RiskLevel,
        reason: str,
    ) -> PermissionResult:

        return PermissionResult(
            decision=PermissionDecision.ALLOW,
            risk=risk,
            reason=reason,
        )

    def _require_approval(
        self,
        risk: RiskLevel,
        reason: str,
    ) -> PermissionResult:

        return PermissionResult(
            decision=PermissionDecision.REQUIRE_APPROVAL,
            risk=risk,
            reason=reason,
        )

    def _deny(
        self,
        risk: RiskLevel,
        reason: str,
    ) -> PermissionResult:

        return PermissionResult(
            decision=PermissionDecision.DENY,
            risk=risk,
            reason=reason,
        )
