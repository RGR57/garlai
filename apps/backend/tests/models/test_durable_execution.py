import unittest

from src.models.durable_execution import (
    ApprovalIdentityMismatchError,
    ApprovalPayloadMismatchError,
    ApprovalRequest,
    DurableStepStatus,
    ExecutionRunStatus,
    canonical_payload_hash,
)


class DurableExecutionDomainTests(unittest.TestCase):
    def test_payload_hash_is_stable_for_equivalent_argument_order(self):
        left = canonical_payload_hash(
            "filesystem",
            "write_file",
            {"path": "a", "content": "x"},
        )
        right = canonical_payload_hash(
            "filesystem",
            "write_file",
            {"content": "x", "path": "a"},
        )

        self.assertEqual(left, right)

    def test_terminal_and_recovery_states_are_distinct(self):
        self.assertTrue(ExecutionRunStatus.COMPLETED.is_terminal)
        self.assertFalse(DurableStepStatus.UNCERTAIN.is_terminal)
        self.assertFalse(DurableStepStatus.KNOWN_FAILED.is_terminal)
        self.assertTrue(DurableStepStatus.COMPLETED.is_terminal)

    def test_approval_validates_exact_execution_and_frozen_payload(self):
        approval = ApprovalRequest.create(
            approval_id="approval-1",
            execution_id="run-1",
            step_id=1,
            operation_id="operation-1",
            tool="filesystem",
            action="write_file",
            arguments={"path": "out.txt", "content": "approved"},
            reason="writes a file",
            risk_level="high",
        )

        approval.assert_authorizes(
            execution_id="run-1",
            payload_hash=canonical_payload_hash(
                "filesystem",
                "write_file",
                {"path": "out.txt", "content": "approved"},
            ),
        )

        with self.assertRaises(ApprovalIdentityMismatchError):
            approval.assert_authorizes(
                execution_id="run-2",
                payload_hash=approval.payload_hash,
            )

        with self.assertRaises(ApprovalPayloadMismatchError):
            approval.assert_authorizes(
                execution_id="run-1",
                payload_hash=canonical_payload_hash(
                    "filesystem",
                    "write_file",
                    {"path": "out.txt", "content": "changed"},
                ),
            )

    def test_approval_rejects_mutated_frozen_arguments(self):
        approval = ApprovalRequest.create(
            approval_id="approval-1",
            execution_id="run-1",
            step_id=1,
            operation_id="operation-1",
            tool="filesystem",
            action="write_file",
            arguments={"path": "out.txt", "content": "approved"},
            reason="writes a file",
            risk_level="high",
        )
        approval.arguments["content"] = "changed"

        with self.assertRaises(ApprovalPayloadMismatchError):
            approval.assert_authorizes(
                execution_id="run-1",
                payload_hash=approval.payload_hash,
            )

    def test_approval_rejects_stored_payload_hash_that_disagrees_with_arguments(self):
        with self.assertRaises(ApprovalPayloadMismatchError):
            ApprovalRequest(
                approval_id="approval-1",
                execution_id="run-1",
                step_id=1,
                operation_id="operation-1",
                tool="filesystem",
                action="write_file",
                arguments={"path": "out.txt", "content": "approved"},
                reason="writes a file",
                risk_level="high",
                payload_hash="not-the-approved-payload",
            )


if __name__ == "__main__":
    unittest.main()
