from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.models.browser import BrowserElement, BrowserObservation, BrowserTarget
from src.models.durable_execution import (
    ApprovalEventType,
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
    ExecutionRunStatus,
    OperationEventType,
    canonical_payload_hash,
)
from src.models.execution_state import ExecutionState
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)
from src.services.approval_service import ApprovalService
from src.services.browser_session_service import BrowserSessionService
from src.services.context_builder import ContextBuilder
from src.services.executor_service import ExecutorService
from src.services.fake_browser_provider import FakeBrowserProvider
from src.services.navigation_policy import LocalFixtureNavigationPolicy
from src.services.permission_service import PermissionService
from src.services.variable_resolver import VariableResolver
from src.tools.browser.browser_submit_tool import BrowserSubmitTool
from src.tools.tool_manager import ToolManager


URL = "http://127.0.0.1:8123/signup"
CHANGED_URL = "http://127.0.0.1:8123/changed-signup"


def _observation(
    *,
    name: str = "Confirm Business signup",
    text: str = "Business - $30/month - supports SSO - 10 users",
    url: str = URL,
    duplicate: bool = False,
) -> BrowserObservation:
    element = BrowserElement(
        element_ref="signup:confirm",
        role="button",
        accessible_name=name,
        form_name="Business signup",
        text_context=text,
        semantic_fingerprint="button|confirm-signup|business",
    )
    elements = (element, replace(element, element_ref="signup:confirm-duplicate")) if duplicate else (element,)
    return BrowserObservation(
        observation_id="signup-observation",
        browser_session_id="fixture-session",
        url=url,
        title="Business signup",
        visible_text=text,
        elements=elements,
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


async def _runtime(tmp_path, execution_id: str, target: BrowserTarget):
    repository = SQLiteDurableExecutionRepository(tmp_path / f"{execution_id}.sqlite3")
    await repository.initialize()
    await repository.create_planning_run(ExecutionRun(execution_id=execution_id, objective="Confirm signup"))
    arguments = {"target": target.to_payload()}
    await repository.persist_validated_plan(
        execution_id,
        [
            DurableStep(
                step_id=1,
                ordinal=0,
                action="Confirm Business signup",
                tool="browser_submit",
                arguments=arguments,
                operation_id=f"operation-{execution_id}",
                payload_hash=canonical_payload_hash("browser_submit", "Confirm Business signup", arguments),
            )
        ],
    )
    provider = FakeBrowserProvider({URL: _observation(), CHANGED_URL: _observation(url=CHANGED_URL)})
    sessions = BrowserSessionService(
        repository,
        provider,
        LocalFixtureNavigationPolicy("http://127.0.0.1:8123"),
    )
    await sessions.navigate(execution_id, URL)
    manager = ToolManager()
    manager.register(BrowserSubmitTool(sessions))
    executor = ExecutorService(
        llm=None,
        context_builder=ContextBuilder(),
        tool_manager=manager,
        variable_resolver=VariableResolver(),
        permission_service=PermissionService(),
        durable_repository=repository,
    )
    return repository, provider, sessions, executor, ApprovalService(manager, repository, executor)


async def _request_approval(executor: ExecutorService, repository, execution_id: str):
    result = await executor.execute_ready_step(execution_id, 1, [], ExecutionState())
    assert result.success is False
    assert "Approval required" in (result.error or "")
    return await repository.get_pending_approval(execution_id)


@pytest.mark.anyio
async def test_approved_submit_dispatches_exactly_once_and_persists_success(tmp_path):
    target = _target("run-happy", _observation())
    repository, provider, _sessions, executor, approvals = await _runtime(tmp_path, "run-happy", target)
    approval = await _request_approval(executor, repository, "run-happy")

    result = await approvals.approve_durable("run-happy", approval.approval_id)

    loaded = await repository.load("run-happy")
    assert result.success is True
    assert [action for action, _target in provider.actions] == ["submit"]
    assert loaded.status is ExecutionRunStatus.COMPLETED
    assert loaded.steps[0].status is DurableStepStatus.COMPLETED
    assert await repository.operation_events("operation-run-happy") == [
        OperationEventType.INTENT_RECORDED,
        OperationEventType.COMPLETED,
    ]


@pytest.mark.anyio
async def test_rejected_submit_never_claims_or_dispatches(tmp_path):
    target = _target("run-rejected", _observation())
    repository, provider, _sessions, executor, approvals = await _runtime(tmp_path, "run-rejected", target)
    approval = await _request_approval(executor, repository, "run-rejected")

    await approvals.reject_durable("run-rejected", approval.approval_id)

    loaded = await repository.load("run-rejected")
    assert provider.actions == []
    assert loaded.status is ExecutionRunStatus.FAILED
    assert loaded.steps[0].status is DurableStepStatus.REJECTED
    assert await repository.operation_events("operation-run-rejected") == []


@pytest.mark.anyio
async def test_submit_before_approval_is_blocked_by_permission_authority(tmp_path):
    target = _target("run-unapproved", _observation())
    repository, provider, _sessions, executor, _approvals = await _runtime(tmp_path, "run-unapproved", target)

    await _request_approval(executor, repository, "run-unapproved")

    loaded = await repository.load("run-unapproved")
    assert provider.actions == []
    assert loaded.status is ExecutionRunStatus.WAITING_APPROVAL
    assert loaded.steps[0].status is DurableStepStatus.WAITING_APPROVAL


@pytest.mark.anyio
@pytest.mark.parametrize(
    "current, changed_url",
    [
        (_observation(text="Business - $50/month - supports SSO - 10 users"), None),
        (_observation(name="Confirm Pro signup", text="Pro - $30/month - supports SSO - 10 users"), None),
        (_observation(duplicate=True), None),
        (_observation(url=CHANGED_URL), CHANGED_URL),
    ],
    ids=["price", "plan-target", "ambiguous-target", "destination"],
)
async def test_stale_approved_submit_is_invalidated_before_dispatch(
    tmp_path,
    current: BrowserObservation,
    changed_url: str | None,
):
    target = _target("run-stale", _observation())
    repository, provider, sessions, executor, approvals = await _runtime(tmp_path, "run-stale", target)
    approval = await _request_approval(executor, repository, "run-stale")
    provider.set_page(current.url, current)
    if changed_url is not None:
        await sessions.navigate("run-stale", changed_url)

    result = await approvals.approve_durable("run-stale", approval.approval_id)

    restored = SQLiteDurableExecutionRepository(repository.database_path)
    loaded = await restored.load("run-stale")
    invalidated = await restored.get_approval("run-stale", approval.approval_id)
    assert result.success is False
    assert provider.actions == []
    assert invalidated.event_type is ApprovalEventType.INVALIDATED
    assert loaded.status is ExecutionRunStatus.RECOVERY_REQUIRED
    assert loaded.steps[0].status is DurableStepStatus.KNOWN_FAILED
    assert await restored.operation_events("operation-run-stale") == []
    with pytest.raises(ValueError, match="no longer pending"):
        await approvals.approve_durable("run-stale", approval.approval_id)


@pytest.mark.anyio
async def test_approval_hash_binds_material_semantic_target_facts(tmp_path):
    original = {"target": _target("run-hash", _observation()).to_payload()}
    changed = {"target": _target("run-hash", _observation(text="Business - $50/month - supports SSO - 10 users")).to_payload()}

    assert canonical_payload_hash("browser_submit", "Confirm Business signup", original) != canonical_payload_hash(
        "browser_submit", "Confirm Business signup", changed
    )


@pytest.mark.anyio
async def test_cross_execution_cannot_reuse_an_approval_or_browser_target(tmp_path):
    target_a = _target("run-a", _observation())
    repository_a, provider_a, _sessions_a, executor_a, approvals_a = await _runtime(tmp_path, "run-a", target_a)
    approval_a = await _request_approval(executor_a, repository_a, "run-a")

    target_b = _target("run-a", _observation())
    repository_b, provider_b, _sessions_b, executor_b, approvals_b = await _runtime(tmp_path, "run-b", target_b)
    with pytest.raises(KeyError, match="Unknown approval"):
        await approvals_b.approve_durable("run-b", approval_a.approval_id)
    approval_b = await _request_approval(executor_b, repository_b, "run-b")

    result = await approvals_b.approve_durable("run-b", approval_b.approval_id)

    loaded = await repository_b.load("run-b")
    assert result.success is False
    assert provider_a.actions == []
    assert provider_b.actions == []
    assert loaded.status is ExecutionRunStatus.RECOVERY_REQUIRED
    assert (await repository_b.get_approval("run-b", approval_b.approval_id)).event_type is ApprovalEventType.INVALIDATED
