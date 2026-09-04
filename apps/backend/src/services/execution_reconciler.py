from __future__ import annotations

from typing import Protocol

from src.models.browser import BrowserObservation, BrowserTarget
from src.models.durable_execution import (
    DurableStepStatus,
    ExecutionRun,
    OrphanedOperation,
)
from src.repositories.durable_execution_repository import DurableExecutionRepository
from src.services.browser_session_service import BrowserSessionService


class ExecutionReconciler(Protocol):
    """Rebuild external facts for a durable run without replaying work."""

    async def reconcile(
        self,
        run: ExecutionRun,
        orphaned_operations: list[OrphanedOperation],
    ) -> None:
        """Persist current external facts before generic recovery chooses a next step."""


class BrowserExecutionReconciler:
    """Observation-first recovery for one execution-owned browser session."""

    def __init__(
        self,
        repository: DurableExecutionRepository,
        browser_sessions: BrowserSessionService,
    ) -> None:
        self.repository = repository
        self.browser_sessions = browser_sessions

    async def reconcile(
        self,
        run: ExecutionRun,
        orphaned_operations: list[OrphanedOperation],
    ) -> None:
        browser = run.execution_context.get("browser")
        if not isinstance(browser, dict):
            return
        last_verified_url = browser.get("last_verified_url")
        if not isinstance(last_verified_url, str) or not last_verified_url:
            await self.repository.record_reconciliation(
                run.execution_id,
                {"browser": {"reconciliation": {"status": "missing_url"}}},
                "Browser recovery cannot continue without a verified destination.",
            )
            return

        try:
            observation = await self.browser_sessions.observe_for_recovery(
                run.execution_id,
                last_verified_url,
            )
        except ValueError as exc:
            await self.repository.record_reconciliation(
                run.execution_id,
                {"browser": {"reconciliation": {"status": "observation_failed"}}},
                f"Browser recovery observation failed: {exc}",
            )
            return

        patch = self._observation_patch(observation)
        submit_orphans = self._browser_submit_orphans(run, orphaned_operations)
        if submit_orphans:
            await self._reconcile_orphaned_submit(
                run,
                submit_orphans[0],
                observation.visible_text,
                patch,
            )
            return

        await self.repository.record_reconciliation(
            run.execution_id,
            patch,
            self._prepared_state_mismatch_reason(run, observation),
        )

    @staticmethod
    def _observation_patch(observation: BrowserObservation) -> dict:
        return {
            "browser": {
                "session_id": observation.browser_session_id,
                "last_verified_url": observation.url,
                "latest_observation": observation.to_payload(),
                "reconciliation": {
                    "observation": observation.to_payload(),
                    "status": "observed",
                },
            }
        }

    @staticmethod
    def _browser_submit_orphans(
        run: ExecutionRun,
        orphaned_operations: list[OrphanedOperation],
    ) -> list[OrphanedOperation]:
        browser_submit_ids = {
            step.operation_id
            for step in run.steps
            if step.tool == "browser_submit" and step.operation_id is not None
        }
        return [
            orphan
            for orphan in orphaned_operations
            if orphan.operation_id in browser_submit_ids
        ]

    async def _reconcile_orphaned_submit(
        self,
        run: ExecutionRun,
        orphan: OrphanedOperation,
        visible_text: str,
        patch: dict,
    ) -> None:
        step = next(item for item in run.steps if item.step_id == orphan.step_id)
        arguments = step.resolved_arguments or step.arguments
        success_text = arguments.get("expected_success_text")
        if isinstance(success_text, str) and success_text and success_text in visible_text:
            claim = await self.repository.recover_orphaned_operation_claim(
                orphan.execution_id,
                orphan.step_id,
                orphan.operation_id,
            )
            if claim.granted:
                await self.repository.record_operation_outcome(
                    claim,
                    DurableStepStatus.COMPLETED,
                    result={"output": "Browser submit confirmed during recovery."},
                    execution_context_patch=patch,
                )
            return
        await self.repository.record_reconciliation(run.execution_id, patch)

    @staticmethod
    def _prepared_state_mismatch_reason(
        run: ExecutionRun,
        observation: BrowserObservation,
    ) -> str | None:
        browser = run.execution_context.get("browser")
        if not isinstance(browser, dict):
            return None
        actions = browser.get("actions")
        if not isinstance(actions, dict):
            return None
        for receipt in actions.values():
            if (
                not isinstance(receipt, dict)
                or receipt.get("action") not in {"select", "fill"}
            ):
                continue
            try:
                target = BrowserTarget.from_payload(receipt.get("target"))
            except ValueError:
                return "Browser prepared-state facts are invalid and require recovery."
            if not BrowserSessionService.target_matches(observation, target):
                return "Browser prepared state changed since the durable checkpoint."
        return None
