from datetime import datetime, timezone

import pytest

from src.models.browser import BrowserElement, BrowserObservation, BrowserTarget
from src.models.durable_execution import (
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
    ExecutionRunStatus,
    OperationEventType,
    canonical_payload_hash,
)
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)
from src.services.browser_session_service import BrowserSessionService
from src.services.execution_reconciler import BrowserExecutionReconciler
from src.services.fake_browser_provider import FakeBrowserProvider
from src.services.navigation_policy import LocalFixtureNavigationPolicy
from src.services.recovery_service import RecoveryService


URL = "http://127.0.0.1:8123/signup"
REVIEW_URL = "http://127.0.0.1:8123/review"


class RecordingFakeBrowserProvider(FakeBrowserProvider):
    def __init__(self, pages) -> None:
        super().__init__(pages)
        self.visits: list[str] = []

    async def navigate(self, session, url, navigation_policy):
        self.visits.append(url)
        return await super().navigate(session, url, navigation_policy)


def _observation(
    *,
    url: str = URL,
    name: str = "Business signup name",
    text: str = "Business - $30/month - supports SSO - 10 users",
) -> BrowserObservation:
    element = BrowserElement(
        element_ref="signup:field",
        role="textbox",
        accessible_name=name,
        label="Name",
        form_name="Business signup",
        text_context=text,
        semantic_fingerprint="textbox|signup-name|business",
    )
    return BrowserObservation(
        observation_id="signup-observation",
        browser_session_id="fixture-session",
        url=url,
        title="Business signup",
        visible_text=text,
        elements=(element,),
        observed_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
        navigation_sequence=1,
        page_fingerprint="signup-v1",
    )


def _target(execution_id: str, observation: BrowserObservation) -> BrowserTarget:
    element = observation.elements[0]
    return BrowserTarget(
        browser_session_id=f"browser-{execution_id}",
        observation_id=observation.observation_id,
        element_ref=element.element_ref,
        observed_url=observation.url,
        role=element.role,
        accessible_name=element.accessible_name,
        label=element.label,
        form_name=element.form_name,
        text_context=element.text_context,
        semantic_fingerprint=element.semantic_fingerprint,
        is_sensitive=element.is_sensitive,
    )


async def _repository(tmp_path, execution_id: str, step: DurableStep):
    repository = SQLiteDurableExecutionRepository(tmp_path / f"{execution_id}.sqlite3")
    await repository.initialize()
    await repository.create_planning_run(
        ExecutionRun(execution_id=execution_id, objective="Prepare a Business signup")
    )
    await repository.persist_validated_plan(execution_id, [step])
    return repository


def _sessions(repository, provider):
    return BrowserSessionService(
        repository,
        provider,
        LocalFixtureNavigationPolicy("http://127.0.0.1:8123"),
    )


@pytest.mark.anyio
async def test_fresh_recovery_reobserves_prepared_state_without_replaying_fill(tmp_path):
    execution_id = "run-prepared"
    initial = _observation()
    target = _target(execution_id, initial)
    step = DurableStep(
        step_id=1,
        ordinal=0,
        action="prepare name",
        tool="browser_fill",
        arguments={"target": target.to_payload(), "value": "GARL Test"},
        status=DurableStepStatus.COMPLETED,
        operation_id="operation-fill",
        payload_hash="fill-payload",
        result={"output": "prepared"},
    )
    repository = await _repository(tmp_path, execution_id, step)
    first = _sessions(repository, RecordingFakeBrowserProvider({URL: initial}))
    await first.navigate(execution_id, URL)
    await first.fill(execution_id, target, "GARL Test", "operation-fill")

    after_restart_provider = RecordingFakeBrowserProvider({URL: initial})
    after_restart = _sessions(repository, after_restart_provider)
    decision = await RecoveryService(
        repository,
        reconciler=BrowserExecutionReconciler(repository, after_restart),
    ).prepare_resume(execution_id)

    loaded = await repository.load(execution_id)
    assert decision.status is ExecutionRunStatus.RUNNING
    assert after_restart_provider.visits == [URL]
    assert after_restart_provider.actions == []
    assert loaded.execution_context["browser"]["reconciliation"]["observation"]["url"] == URL


@pytest.mark.anyio
async def test_selection_persists_the_post_action_destination_for_recovery(tmp_path):
    class NavigatingSelectProvider(FakeBrowserProvider):
        async def select(self, session, target):
            await super().select(session, target)
            self._session(session).current_url = REVIEW_URL

    execution_id = "run-selection-destination"
    initial = _observation()
    target = _target(execution_id, initial)
    step = DurableStep(
        step_id=1,
        ordinal=0,
        action="choose Business",
        tool="browser_select",
        arguments={"target": target.to_payload()},
        operation_id="operation-select",
        payload_hash="select-payload",
    )
    repository = await _repository(tmp_path, execution_id, step)
    provider = NavigatingSelectProvider({URL: initial, REVIEW_URL: _observation(url=REVIEW_URL)})
    sessions = _sessions(repository, provider)
    await sessions.navigate(execution_id, URL)

    receipt = await sessions.select(execution_id, target, "operation-select")
    loaded = await repository.load(execution_id)
    fresh_provider = RecordingFakeBrowserProvider({REVIEW_URL: _observation(url=REVIEW_URL)})
    decision = await RecoveryService(
        repository,
        reconciler=BrowserExecutionReconciler(
            repository,
            _sessions(repository, fresh_provider),
        ),
    ).prepare_resume(execution_id)

    assert receipt["observed_url"] == REVIEW_URL
    assert loaded.execution_context["browser"]["last_verified_url"] == REVIEW_URL
    assert fresh_provider.visits == [REVIEW_URL]
    assert decision.may_execute is True


@pytest.mark.anyio
async def test_recovery_persists_changed_prepared_target_as_recovery_required(tmp_path):
    execution_id = "run-changed"
    initial = _observation()
    target = _target(execution_id, initial)
    step = DurableStep(
        step_id=1,
        ordinal=0,
        action="prepare name",
        tool="browser_fill",
        arguments={"target": target.to_payload(), "value": "GARL Test"},
        status=DurableStepStatus.COMPLETED,
        operation_id="operation-fill",
        payload_hash="fill-payload",
        result={"output": "prepared"},
    )
    repository = await _repository(tmp_path, execution_id, step)
    first = _sessions(repository, RecordingFakeBrowserProvider({URL: initial}))
    await first.navigate(execution_id, URL)
    await first.fill(execution_id, target, "GARL Test", "operation-fill")

    changed = _observation(text="Business - $50/month - supports SSO - 10 users")
    provider = RecordingFakeBrowserProvider({URL: changed})
    decision = await RecoveryService(
        repository,
        reconciler=BrowserExecutionReconciler(repository, _sessions(repository, provider)),
    ).prepare_resume(execution_id)

    loaded = await repository.load(execution_id)
    assert decision.status is ExecutionRunStatus.RECOVERY_REQUIRED
    assert decision.may_execute is False
    assert provider.actions == []
    assert "changed" in loaded.execution_context["recovery"]["reason"]


@pytest.mark.anyio
async def test_recovery_confirms_orphaned_submit_only_from_visible_success(tmp_path):
    execution_id = "run-orphan-success"
    initial = _observation()
    target = _target(execution_id, initial)
    arguments = {
        "target": target.to_payload(),
        "expected_success_text": "Signup complete",
    }
    step = DurableStep(
        step_id=1,
        ordinal=0,
        action="Confirm Business signup",
        tool="browser_submit",
        arguments=arguments,
        operation_id="operation-submit",
        payload_hash=canonical_payload_hash("browser_submit", "Confirm Business signup", arguments),
    )
    repository = await _repository(tmp_path, execution_id, step)
    first = _sessions(repository, RecordingFakeBrowserProvider({URL: initial}))
    await first.navigate(execution_id, URL)
    claim = await repository.claim_operation(
        execution_id,
        1,
        "operation-submit",
        step.payload_hash,
    )
    assert claim.granted is True

    success = _observation(name="Signup complete", text="Signup complete")
    provider = RecordingFakeBrowserProvider({URL: success})
    decision = await RecoveryService(
        repository,
        reconciler=BrowserExecutionReconciler(repository, _sessions(repository, provider)),
    ).prepare_resume(execution_id)

    loaded = await repository.load(execution_id)
    assert decision.may_execute is False
    assert provider.actions == []
    assert loaded.steps[0].status is DurableStepStatus.COMPLETED
    assert await repository.operation_events("operation-submit") == [
        OperationEventType.INTENT_RECORDED,
        OperationEventType.COMPLETED,
    ]


@pytest.mark.anyio
async def test_recovery_does_not_resubmit_orphaned_submit_without_visible_proof(tmp_path):
    execution_id = "run-orphan-unknown"
    initial = _observation()
    target = _target(execution_id, initial)
    arguments = {
        "target": target.to_payload(),
        "expected_success_text": "Signup complete",
    }
    step = DurableStep(
        step_id=1,
        ordinal=0,
        action="Confirm Business signup",
        tool="browser_submit",
        arguments=arguments,
        operation_id="operation-submit",
        payload_hash=canonical_payload_hash("browser_submit", "Confirm Business signup", arguments),
    )
    repository = await _repository(tmp_path, execution_id, step)
    first = _sessions(repository, RecordingFakeBrowserProvider({URL: initial}))
    await first.navigate(execution_id, URL)
    claim = await repository.claim_operation(
        execution_id,
        1,
        "operation-submit",
        step.payload_hash,
    )
    assert claim.granted is True

    provider = RecordingFakeBrowserProvider({URL: initial})
    decision = await RecoveryService(
        repository,
        reconciler=BrowserExecutionReconciler(repository, _sessions(repository, provider)),
    ).prepare_resume(execution_id)

    loaded = await repository.load(execution_id)
    assert decision.status is ExecutionRunStatus.RECOVERY_REQUIRED
    assert provider.actions == []
    assert loaded.steps[0].status is DurableStepStatus.UNCERTAIN
    assert await repository.operation_events("operation-submit") == [
        OperationEventType.INTENT_RECORDED,
        OperationEventType.UNCERTAIN,
    ]
