import unittest

from src.models.tool_risk import PermissionDecision
from src.services.permission_service import PermissionService


class ExecutionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.permission = PermissionService()

    def test_filesystem_write_is_consequential_and_read_is_read_only(self):
        write = self.permission.evaluate(
            "filesystem",
            {"action": "write_file", "path": "out.txt", "content": "x"},
        )
        read = self.permission.evaluate(
            "filesystem",
            {"action": "read_file", "path": "out.txt"},
        )

        self.assertTrue(write.execution_policy.is_consequential)
        self.assertFalse(read.execution_policy.is_consequential)
        self.assertTrue(read.execution_policy.retry_known_failure)

    def test_terminal_install_is_consequential_when_approval_is_required(self):
        result = self.permission.evaluate(
            "terminal",
            {"query": "pip install example-package"},
        )

        self.assertEqual(result.decision, PermissionDecision.REQUIRE_APPROVAL)
        self.assertTrue(result.execution_policy.is_consequential)
        self.assertFalse(result.execution_policy.retry_known_failure)

    def test_unknown_tool_is_denied_and_never_retry_safe(self):
        result = self.permission.evaluate("unknown", {})

        self.assertEqual(result.decision, PermissionDecision.DENY)
        self.assertTrue(result.execution_policy.is_consequential)
        self.assertFalse(result.execution_policy.retry_known_failure)

    def test_browser_navigation_and_observation_are_allowed_read_oriented_actions(self):
        for tool_name in ("browser_navigate", "browser_observe"):
            result = self.permission.evaluate(tool_name, {})

            self.assertEqual(result.decision, PermissionDecision.ALLOW)
            self.assertFalse(result.execution_policy.is_consequential)
            self.assertTrue(result.execution_policy.retry_known_failure)

    def test_browser_preparation_is_allowed_but_conservative(self):
        for tool_name in ("browser_select", "browser_fill"):
            result = self.permission.evaluate(tool_name, {})

            self.assertEqual(result.decision, PermissionDecision.ALLOW)
            self.assertTrue(result.execution_policy.is_consequential)
            self.assertFalse(result.execution_policy.retry_known_failure)

    def test_browser_submit_requires_high_risk_approval(self):
        result = self.permission.evaluate("browser_submit", {})

        self.assertEqual(result.decision, PermissionDecision.REQUIRE_APPROVAL)
        self.assertTrue(result.execution_policy.is_consequential)
        self.assertFalse(result.execution_policy.retry_known_failure)


if __name__ == "__main__":
    unittest.main()
