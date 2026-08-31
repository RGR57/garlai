# GARL Core V1 Durable Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make one GARL objective durable across application reconstruction without repeating completed or ambiguous consequential work.

**Architecture:** Add a domain-facing durable execution repository and a SQLite implementation that stores a compact execution aggregate plus append-only approval and operation journal facts. The runtime persists a validated plan and resumes from durable step state; consequential execution uses a transactional atomic claim before an external call and defaults to recovery-required uncertainty when the outcome cannot be proven.

**Tech Stack:** Python 3.13, FastAPI, standard-library sqlite3, asyncio.to_thread, Pydantic, dataclasses, pytest, unittest async tests.

**Spec:** docs/superpowers/specs/2026-08-31-garl-durable-execution-design.md

## Global Constraints

- Use standard-library sqlite3; do not introduce an ORM, PostgreSQL, Redis, queues, or background scheduling.
- Keep SQL and SQLite connection lifecycle inside the SQLite repository implementation.
- Enable foreign_keys, configure a bounded busy timeout, use WAL for the V1 local-file access pattern, and keep every transaction short.
- Never hold a SQLite transaction across a tool, LLM, network, terminal, filesystem, or other external call.
- execution_id is authoritative. conversation_id is routing metadata only and cannot select an arbitrary run for state-changing work.
- Persist only constrained, validated JSON execution context; never persist credentials, API keys, tokens, raw secrets, arbitrary Python objects, or pickle data.
- Persist a validated plan before execution; restart must not regenerate it merely because the process was reconstructed.
- Completed steps never execute again. A consequential operation with committed intent but no confirmed terminal outcome is UNCERTAIN and cannot retry automatically.
- Approval binds to execution_id, approval_id, operation_id, step, tool/action, and canonical resolved-argument payload hash.
- Preserve the current mounted chat route and leave legacy src/agents and router structure untouched.
- Mandatory tests use the fake LLM and temporary SQLite databases; live provider tests remain opt-in.

---

## File Structure

- Create apps/backend/src/models/durable_execution.py: durable run/step/journal/approval DTOs, legal-state enums, and canonical payload hashing inputs.
- Create apps/backend/src/repositories/durable_execution_repository.py: domain repository protocol and atomic transition result types.
- Create apps/backend/src/repositories/sqlite_durable_execution_repository.py: SQLite schema migration, connection lifecycle, JSON codecs, aggregate persistence, journals, and conditional claims.
- Create apps/backend/src/services/execution_policy.py: policy classification derived from current permission/tool metadata, not storage rules.
- Create apps/backend/src/services/durable_execution_service.py: planning and resuming one persisted execution.
- Create apps/backend/src/services/recovery_service.py: explicit restart classification and safe resume preparation.
- Modify apps/backend/src/services/executor_service.py: execute only durably claimed ready steps and checkpoint outcomes.
- Modify apps/backend/src/services/approval_service.py: persist immutable approvals and resume the exact operation through an atomic claim.
- Modify apps/backend/src/services/agent_service.py, cognitive_pipeline.py, and conversation_service.py: make the durable run the active execution owner while retaining current objects as runtime views.
- Modify apps/backend/src/core/config.py, core/dependencies.py, and core/lifespan.py: configure database path, inject repository, initialize schema.
- Modify apps/backend/src/schemas/chat.py and src/api/v1/chat.py: expose explicit execution/approval identities without moving the route.
- Create focused repository, service, API, and process-reconstruction tests.

### Task 1: Durable Domain Types and Canonical Payloads

**Files:**
- Create: apps/backend/src/models/durable_execution.py
- Test: apps/backend/tests/models/test_durable_execution.py

**Interfaces:**
- Produces ExecutionRunStatus, DurableStepStatus, OperationEventType, ApprovalEventType, ExecutionRun, DurableStep, ApprovalRequest, OperationClaim, JsonValue, DurableStateCorruptionError, ApprovalPayloadMismatchError, and ApprovalIdentityMismatchError.
- Produces canonical_payload_hash(tool: str, action: str, arguments: dict[str, Any]) -> str.
- Later tasks consume only these domain DTOs and never SQLite rows.

- [ ] **Step 1: Write failing state and canonical-payload tests**

~~~python
def test_payload_hash_is_stable_for_equivalent_argument_order():
    left = canonical_payload_hash("filesystem", "write_file", {"path": "a", "content": "x"})
    right = canonical_payload_hash("filesystem", "write_file", {"content": "x", "path": "a"})
    assert left == right


def test_terminal_and_recovery_states_are_distinct():
    assert ExecutionRunStatus.COMPLETED.is_terminal is True
    assert DurableStepStatus.UNCERTAIN.is_terminal is False
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: cd apps/backend; python -m pytest tests/models/test_durable_execution.py -v

Expected: FAIL because src.models.durable_execution does not exist.

- [ ] **Step 3: Implement the smallest explicit model**

~~~python
class ExecutionRunStatus(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    RECOVERY_REQUIRED = "recovery_required"
    COMPLETED = "completed"
    FAILED = "failed"


class DurableStepStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    KNOWN_FAILED = "known_failed"
    WAITING_APPROVAL = "waiting_approval"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


def canonical_payload_hash(tool: str, action: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps({"tool": tool, "action": action, "arguments": arguments}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OperationClaim:
    granted: bool
    execution_id: str
    step_id: int
    operation_id: str
    attempt_id: str | None = None

    @classmethod
    def denied(cls, execution_id: str, step_id: int, operation_id: str) -> "OperationClaim":
        return cls(False, execution_id, step_id, operation_id)
~~~

Define legal transition maps and validate DTO JSON-facing fields as mappings, lists, or scalar values.

- [ ] **Step 4: Run focused and regression tests**

Run: cd apps/backend; python -m pytest tests/models/test_durable_execution.py tests/services/test_executor_service.py -v

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/src/models/durable_execution.py apps/backend/tests/models/test_durable_execution.py
git commit -m "feat: define durable execution domain state"
~~~

### Task 2: Durable Repository Contract and SQLite Migration

**Files:**
- Create: apps/backend/src/repositories/durable_execution_repository.py
- Create: apps/backend/src/repositories/sqlite_durable_execution_repository.py
- Test: apps/backend/tests/repositories/test_sqlite_durable_execution_repository.py

**Interfaces:**
- Produces async DurableExecutionRepository.initialize, create_planning_run, persist_validated_plan, load, list_recoverable, and delete_for_test.
- Produces SQLiteDurableExecutionRepository(database_path: Path, busy_timeout_ms: int = 5000).
- Consumes Task 1 DTOs only.

- [ ] **Step 1: Write failing schema initialization tests**

~~~python
async def test_initialize_is_idempotent_and_enables_foreign_keys(tmp_path):
    repository = SQLiteDurableExecutionRepository(tmp_path / "durable.sqlite3")
    await repository.initialize()
    await repository.initialize()
    assert await repository.schema_versions() == [1]
    assert await repository.foreign_keys_enabled() is True
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: cd apps/backend; python -m pytest tests/repositories/test_sqlite_durable_execution_repository.py::test_initialize_is_idempotent_and_enables_foreign_keys -v

Expected: FAIL because the SQLite repository does not exist.

- [ ] **Step 3: Implement protocol, connection lifecycle, and migration 1**

~~~python
class DurableExecutionRepository(Protocol):
    async def initialize(self) -> None: ...
    async def create_planning_run(self, run: ExecutionRun) -> None: ...
    async def persist_validated_plan(self, execution_id: str, steps: list[DurableStep]) -> None: ...
    async def load(self, execution_id: str) -> ExecutionRun: ...


def _connect(self) -> sqlite3.Connection:
    connection = sqlite3.connect(self.database_path, isolation_level=None)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection
~~~

Use asyncio.to_thread for synchronous repository work. Migration 1 creates schema_migrations, execution_runs, execution_steps, operation_journal, and approval_journal with foreign keys and stable unique identifiers.

- [ ] **Step 4: Run focused repository tests**

Run: cd apps/backend; python -m pytest tests/repositories/test_sqlite_durable_execution_repository.py -v

Expected: PASS; version 1 appears once and no connection is shared globally.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/src/repositories/durable_execution_repository.py apps/backend/src/repositories/sqlite_durable_execution_repository.py apps/backend/tests/repositories/test_sqlite_durable_execution_repository.py
git commit -m "feat: add SQLite durable execution schema"
~~~

### Task 3: Aggregate Persistence and Validated JSON Load

**Files:**
- Modify: apps/backend/src/repositories/sqlite_durable_execution_repository.py
- Test: apps/backend/tests/repositories/test_sqlite_durable_execution_repository.py

**Interfaces:**
- Produces load(execution_id: str) -> ExecutionRun containing persisted plan, variables, steps, result/error metadata, artifacts, and execution-scoped context.
- Raises DurableStateCorruptionError for structurally invalid persisted constrained JSON.

- [ ] **Step 1: Write failing fresh-repository and invalid-data tests**

~~~python
async def test_fresh_repository_loads_persisted_run_and_completed_step(tmp_path):
    path = tmp_path / "restart.sqlite3"
    first = SQLiteDurableExecutionRepository(path)
    await save_run_with_completed_step(first, execution_id="run-1")
    second = SQLiteDurableExecutionRepository(path)
    loaded = await second.load("run-1")
    assert loaded.objective == "prepare a report"
    assert loaded.steps[0].status is DurableStepStatus.COMPLETED


async def test_load_rejects_invalid_constrained_json(repository):
    await repository.insert_invalid_json_for_test("run-corrupt")
    with pytest.raises(DurableStateCorruptionError):
        await repository.load("run-corrupt")
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: cd apps/backend; python -m pytest tests/repositories/test_sqlite_durable_execution_repository.py -k "fresh_repository or invalid_constrained" -v

Expected: FAIL because aggregate write/load and validation are absent.

- [ ] **Step 3: Implement explicit codecs and aggregate transition**

~~~python
def _encode_json(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _decode_mapping(raw: str, field: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise DurableStateCorruptionError(f"{field} must decode to an object")
    return value
~~~

persist_validated_plan inserts canonical step rows and conditionally transitions only PLANNING to RUNNING in one transaction. load validates enum values and DTO fields before returning domain objects.

- [ ] **Step 4: Run repository regression tests**

Run: cd apps/backend; python -m pytest tests/repositories/test_sqlite_durable_execution_repository.py -v

Expected: PASS, including a new repository object reading the same file.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/src/repositories/sqlite_durable_execution_repository.py apps/backend/tests/repositories/test_sqlite_durable_execution_repository.py
git commit -m "feat: persist durable execution aggregates"
~~~

### Task 4: Atomic Operation Claims and Journal Facts

**Files:**
- Modify: apps/backend/src/repositories/durable_execution_repository.py
- Modify: apps/backend/src/repositories/sqlite_durable_execution_repository.py
- Test: apps/backend/tests/repositories/test_operation_claims.py

**Interfaces:**
- Produces claim_operation(execution_id, step_id, operation_id, payload_hash) -> OperationClaim.
- Produces record_operation_outcome(claim, outcome) and mark_operation_uncertain(execution_id, step_id, operation_id, reason).
- OperationClaim.granted is the sole permission for a caller to invoke a consequential tool.

- [ ] **Step 1: Write failing concurrent-claim test**

~~~python
async def test_only_one_concurrent_caller_claims_consequential_operation(repository):
    first, second = await asyncio.gather(
        repository.claim_operation("run-1", 1, "operation-1", PAYLOAD_HASH),
        repository.claim_operation("run-1", 1, "operation-1", PAYLOAD_HASH),
    )
    assert sorted([first.granted, second.granted]) == [False, True]
    assert await repository.operation_events("operation-1") == [OperationEventType.INTENT_RECORDED]
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: cd apps/backend; python -m pytest tests/repositories/test_operation_claims.py::test_only_one_concurrent_caller_claims_consequential_operation -v

Expected: FAIL because no conditional claim exists.

- [ ] **Step 3: Implement the short claim transaction**

~~~python
with connection:
    updated = connection.execute(
        "UPDATE execution_steps SET status = ? WHERE execution_id = ? AND step_id = ? AND status = ? AND operation_id = ?",
        ("executing", execution_id, step_id, "pending", operation_id),
    ).rowcount
    if updated != 1:
        return OperationClaim.denied(execution_id, step_id, operation_id)
    connection.execute("INSERT INTO operation_journal (...) VALUES (..., 'intent_recorded', ...)")
    return OperationClaim.granted(execution_id, step_id, operation_id, attempt_id)
~~~

Add a unique operation_id plus INTENT_RECORDED constraint. Do not invoke a tool in this repository method.

- [ ] **Step 4: Run claim and aggregate regression tests**

Run: cd apps/backend; python -m pytest tests/repositories/test_operation_claims.py tests/repositories/test_sqlite_durable_execution_repository.py -v

Expected: PASS; exactly one caller wins and a claimed operation cannot be claimed again.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/src/repositories/durable_execution_repository.py apps/backend/src/repositories/sqlite_durable_execution_repository.py apps/backend/tests/repositories/test_operation_claims.py
git commit -m "feat: journal durable operation claims"
~~~

### Task 5: Execution Policy at the Permission Boundary

**Files:**
- Create: apps/backend/src/services/execution_policy.py
- Modify: apps/backend/src/services/permission_service.py
- Modify: apps/backend/src/tools/base_tool.py
- Test: apps/backend/tests/services/test_execution_policy.py

**Interfaces:**
- Produces ExecutionClassification.READ_ONLY and CONSEQUENTIAL.
- Produces ExecutionPolicy(classification, retry_known_failure, supports_idempotency_key).
- Extends PermissionResult with execution_policy.
- Extends BaseTool with non-breaking supports_idempotency_key: bool = False.

- [ ] **Step 1: Write failing current-tool policy tests**

~~~python
def test_filesystem_write_is_consequential_and_read_is_read_only():
    assert permission.evaluate("filesystem", {"action": "write_file", "path": "out.txt", "content": "x"}).execution_policy.is_consequential
    assert not permission.evaluate("filesystem", {"action": "read_file", "path": "out.txt"}).execution_policy.is_consequential


def test_terminal_install_is_consequential_when_approval_is_required():
    result = permission.evaluate("terminal", {"query": "pip install example-package"})
    assert result.decision is PermissionDecision.REQUIRE_APPROVAL
    assert result.execution_policy.is_consequential
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: cd apps/backend; python -m pytest tests/services/test_execution_policy.py -v

Expected: FAIL because PermissionResult has no execution policy.

- [ ] **Step 3: Implement policy without putting safety decisions in storage**

~~~python
@dataclass(frozen=True)
class ExecutionPolicy:
    classification: ExecutionClassification
    retry_known_failure: bool
    supports_idempotency_key: bool = False

    @property
    def is_consequential(self) -> bool:
        return self.classification is ExecutionClassification.CONSEQUENTIAL
~~~

PermissionService derives the policy from existing tool/action/risk logic. Unknown tools remain denied. The repository only records the policy result as fact.

- [ ] **Step 4: Run policy, permission, and executor regressions**

Run: cd apps/backend; python -m pytest tests/services/test_execution_policy.py tests/services/test_executor_service.py -v

Expected: PASS; DENY and approval behavior remain enforced.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/src/services/execution_policy.py apps/backend/src/services/permission_service.py apps/backend/src/tools/base_tool.py apps/backend/tests/services/test_execution_policy.py
git commit -m "feat: classify GARL execution safety"
~~~

### Task 6: Durable Executor Checkpoints and Post-Intent Uncertainty

**Files:**
- Modify: apps/backend/src/services/executor_service.py
- Modify: apps/backend/src/repositories/durable_execution_repository.py
- Test: apps/backend/tests/services/test_durable_executor_service.py

**Interfaces:**
- Produces execute_ready_step(execution_id, step_id, messages, state) -> StepResult.
- Consequential execution calls claim_operation, then invokes the tool outside a transaction, then records a confirmed outcome or uncertainty.

- [ ] **Step 1: Write failing skip and uncertainty tests**

~~~python
async def test_completed_step_is_not_invoked_again_after_reload(recording_tool, repository):
    await persist_completed_step(repository)
    result = await executor.execute_ready_step("run-1", 1, [], rebuilt_state())
    assert result.metadata["durable_skip"] is True
    assert recording_tool.calls == []


async def test_post_intent_exception_becomes_uncertain(repository, ambiguous_tool):
    result = await executor.execute_ready_step("run-1", 1, [], rebuilt_state())
    assert result.metadata["durable_status"] == "uncertain"
    assert (await repository.load("run-1")).status is ExecutionRunStatus.RECOVERY_REQUIRED
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: cd apps/backend; python -m pytest tests/services/test_durable_executor_service.py -v

Expected: FAIL because executor has no durable checkpoints.

- [ ] **Step 3: Implement the ready-step execution path**

~~~python
claim = await repository.claim_operation(execution_id, step.id, step.operation_id, step.payload_hash)
if not claim.granted:
    return StepResult(step_id=step.id, success=False, error="Operation is already claimed.", metadata={"durable_skip": True})

try:
    tool_result = await tool.execute(**resolved_arguments)
except Exception as exc:
    await repository.mark_operation_uncertain(execution_id, step.id, step.operation_id, type(exc).__name__)
    return StepResult(step_id=step.id, success=False, error="Consequential operation outcome is uncertain.")
~~~

For read-only actions, persist start/result state and use policy-controlled known failure handling. Consequential failure is KNOWN_FAILED only when adapter evidence positively proves no side effect.

- [ ] **Step 4: Run executor and pipeline regression tests**

Run: cd apps/backend; python -m pytest tests/services/test_durable_executor_service.py tests/services/test_executor_service.py tests/services/test_cognitive_pipeline.py -v

Expected: PASS; completed work skips and ambiguous work stops.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/src/services/executor_service.py apps/backend/src/repositories/durable_execution_repository.py apps/backend/tests/services/test_durable_executor_service.py
git commit -m "feat: checkpoint durable tool execution"
~~~

### Task 7: Durable Approval Lifecycle and Payload Immutability

**Files:**
- Modify: apps/backend/src/repositories/durable_execution_repository.py
- Modify: apps/backend/src/repositories/sqlite_durable_execution_repository.py
- Modify: apps/backend/src/services/approval_service.py
- Test: apps/backend/tests/services/test_durable_approval_service.py

**Interfaces:**
- Produces request_approval(request), get_approval(execution_id, approval_id), approve(execution_id, approval_id, approved_payload_hash), and reject(execution_id, approval_id).
- ApprovalService consumes only durable approval identity and the repository-loaded frozen payload.

- [ ] **Step 1: Write failing immutability and concurrent-approval tests**

~~~python
async def test_approved_payload_cannot_authorize_changed_arguments(repository):
    approval = await request_write_approval(repository, content="approved")
    with pytest.raises(ApprovalPayloadMismatchError):
        await repository.approve(approval.execution_id, approval.approval_id, canonical_payload_hash("filesystem", "write_file", {"path": "out.txt", "content": "changed"}))


async def test_concurrent_approvals_execute_exact_operation_at_most_once(service, recording_tool):
    await asyncio.gather(service.approve("run-1", "approval-1"), service.approve("run-1", "approval-1"))
    assert recording_tool.calls == [{"path": "out.txt", "content": "approved"}]
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: cd apps/backend; python -m pytest tests/services/test_durable_approval_service.py -v

Expected: FAIL because approvals exist only in in-memory ExecutionState.

- [ ] **Step 3: Persist immutable approvals and reuse operation claim**

~~~python
stored_approval = await repository.get_approval(execution_id, approval_id)
approval = await repository.approve(execution_id, approval_id, stored_approval.payload_hash)
actual_hash = canonical_payload_hash(approval.tool, approval.action, approval.arguments)
if approval.payload_hash != actual_hash:
    raise ApprovalPayloadMismatchError("Approved payload no longer matches stored authorization.")
return await executor.execute_ready_step(execution_id, approval.step_id, messages=[], state=state)
~~~

The approval transaction conditionally accepts only PENDING. Rejection appends REJECTED, changes step state to REJECTED, and performs zero side effect.

- [ ] **Step 4: Run approval and executor regressions**

Run: cd apps/backend; python -m pytest tests/services/test_durable_approval_service.py tests/services/test_approval_service.py tests/services/test_durable_executor_service.py -v

Expected: PASS; exact payload survives restart and races cannot duplicate execution.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/src/repositories/durable_execution_repository.py apps/backend/src/repositories/sqlite_durable_execution_repository.py apps/backend/src/services/approval_service.py apps/backend/tests/services/test_durable_approval_service.py
git commit -m "feat: persist GARL approval operations"
~~~

### Task 8: Recovery Service and Persisted-Plan Continuation

**Files:**
- Create: apps/backend/src/services/recovery_service.py
- Create: apps/backend/src/services/durable_execution_service.py
- Modify: apps/backend/src/services/cognitive_pipeline.py
- Test: apps/backend/tests/services/test_recovery_service.py

**Interfaces:**
- Produces RecoveryService.prepare_resume(execution_id) -> RecoveryDecision.
- Produces DurableExecutionService.start(objective, execution_context) -> ExecutionRun and resume(execution_id) -> ChatResponse.
- Pipeline consumes a persisted plan and durable cursor instead of regenerating a plan on restart.

- [ ] **Step 1: Write failing recovery tests**

~~~python
async def test_recovery_marks_orphaned_intent_uncertain_and_stops(repository):
    await persist_orphaned_intent(repository, "run-1", "operation-1")
    decision = await RecoveryService(repository).prepare_resume("run-1")
    assert decision.status is ExecutionRunStatus.RECOVERY_REQUIRED
    assert decision.may_execute is False


async def test_recovery_restores_outputs_and_selects_next_pending_step(repository):
    await persist_two_step_run_with_first_complete(repository)
    decision = await RecoveryService(repository).prepare_resume("run-1")
    assert decision.next_step_id == 2
    assert decision.execution_state.variables["step1"] == "first output"
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: cd apps/backend; python -m pytest tests/services/test_recovery_service.py -v

Expected: FAIL because no recovery service loads durable aggregate state.

- [ ] **Step 3: Implement explicit safe recovery**

~~~python
run = await repository.load(execution_id)
if run.status is ExecutionRunStatus.WAITING_APPROVAL:
    return RecoveryDecision.waiting_for_approval(run.pending_approval)
if run.has_orphaned_consequential_intent:
    await repository.mark_operation_uncertain(...)
    return RecoveryDecision.recovery_required(run.execution_id)
return RecoveryDecision.ready(run.execution_id, first_legal_pending_step(run.steps), rebuild_execution_state(run))
~~~

DurableExecutionService creates PLANNING, obtains/validates a plan once, and transactionally persists it as RUNNING. Restart alone never triggers replan.

- [ ] **Step 4: Run recovery and pipeline regressions**

Run: cd apps/backend; python -m pytest tests/services/test_recovery_service.py tests/services/test_cognitive_pipeline.py tests/services/test_durable_executor_service.py -v

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/src/services/recovery_service.py apps/backend/src/services/durable_execution_service.py apps/backend/src/services/cognitive_pipeline.py apps/backend/tests/services/test_recovery_service.py
git commit -m "feat: recover persisted GARL executions"
~~~

### Task 9: Active Runtime Wiring and Explicit Identities

**Files:**
- Modify: apps/backend/src/core/config.py
- Modify: apps/backend/src/core/dependencies.py
- Modify: apps/backend/src/core/lifespan.py
- Modify: apps/backend/src/main.py
- Modify: apps/backend/src/services/agent_service.py
- Modify: apps/backend/src/services/conversation_service.py
- Modify: apps/backend/src/schemas/chat.py
- Modify: apps/backend/src/api/v1/chat.py
- Test: apps/backend/tests/api/test_durable_chat_api.py

**Interfaces:**
- Adds GARL_DURABLE_DB_PATH to Settings.
- ChatRequest accepts optional execution_id and approval_id.
- ChatResponse returns execution_id, run status, and optional pending approval_id.
- State-changing approve/reject/resume requests require explicit durable identity.

- [ ] **Step 1: Write failing API identity and startup tests**

~~~python
def test_same_conversation_cannot_cross_approve_two_runs(client):
    first = start_run(client, conversation_id="shared", objective="first")
    second = start_run(client, conversation_id="shared", objective="second")
    response = client.post("/api/v1/chat", json={"conversation_id": "shared", "message": "approve", "execution_id": first["execution_id"], "approval_id": second["approval_id"]})
    assert response.status_code == 409


def test_lifespan_initializes_durable_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("GARL_DURABLE_DB_PATH", str(tmp_path / "runtime.sqlite3"))
    with TestClient(app):
        assert (tmp_path / "runtime.sqlite3").exists()
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: cd apps/backend; python -m pytest tests/api/test_durable_chat_api.py -v

Expected: FAIL because active requests do not expose durable identities or initialize storage.

- [ ] **Step 3: Wire dependencies and lifespan without global connections**

~~~python
@lru_cache
def get_durable_execution_repository() -> DurableExecutionRepository:
    return SQLiteDurableExecutionRepository(Path(settings.GARL_DURABLE_DB_PATH))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_durable_execution_repository().initialize()
    yield
~~~

A new objective creates a new execution id even for the same conversation id. Approve, reject, and resume use supplied durable ids, never an arbitrary active conversation state. Preserve the mounted chat route.

- [ ] **Step 4: Run API and startup regressions**

Run: cd apps/backend; python -m pytest tests/api/test_durable_chat_api.py tests/api/test_app_startup.py tests/api/test_chat_e2e.py -v

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/src/core/config.py apps/backend/src/core/dependencies.py apps/backend/src/core/lifespan.py apps/backend/src/main.py apps/backend/src/services/agent_service.py apps/backend/src/services/conversation_service.py apps/backend/src/schemas/chat.py apps/backend/src/api/v1/chat.py apps/backend/tests/api/test_durable_chat_api.py
git commit -m "feat: wire durable GARL execution runtime"
~~~

### Task 10: Fresh-Graph Mission Tests and Final Verification

**Files:**
- Create: apps/backend/tests/api/test_durable_execution_e2e.py
- Modify: apps/backend/tests/api/test_chat_e2e.py only if a shared fake durable fixture prevents duplication.
- Modify: apps/backend/requirements.txt only if standard-library sqlite3 proves insufficient; expected change is none.

**Interfaces:**
- Consumes the wired FastAPI/service graph with a temporary SQLite path and deterministic fake LLM.
- Proves a genuinely fresh service graph continues the same execution id safely.

- [ ] **Step 1: Write failing process-reconstruction mission tests**

~~~python
def test_multistep_objective_resumes_after_fresh_graph_without_duplicate_work(tmp_path):
    first_graph, first_tool = build_durable_graph(tmp_path / "mission.sqlite3")
    run = start_two_step_objective(first_graph)
    assert first_tool.calls == ["step-1"]

    second_graph, second_tool = build_durable_graph(tmp_path / "mission.sqlite3")
    response = second_graph.resume(run.execution_id)
    assert second_tool.calls == ["step-2"]
    assert load_run(second_graph, run.execution_id).status is ExecutionRunStatus.COMPLETED


def test_pending_approval_survives_fresh_graph_with_zero_side_effect(tmp_path):
    first_graph, first_tool = build_durable_graph(tmp_path / "approval.sqlite3")
    run = start_approval_required_objective(first_graph)
    second_graph, second_tool = build_durable_graph(tmp_path / "approval.sqlite3")
    assert inspect_pending(second_graph, run.execution_id).approval_id
    assert first_tool.calls == [] and second_tool.calls == []


def test_approval_after_restart_executes_the_frozen_operation_once(tmp_path):
    path = tmp_path / "approved.sqlite3"
    first_graph, _ = build_durable_graph(path)
    run = start_approval_required_objective(first_graph)
    second_graph, second_tool = build_durable_graph(path)
    approval = inspect_pending(second_graph, run.execution_id)
    second_graph.approve(run.execution_id, approval.approval_id)
    assert second_tool.calls == [{"path": "out.txt", "content": "approved"}]
    assert load_run(second_graph, run.execution_id).steps[0].status is DurableStepStatus.COMPLETED
~~~

Add these concrete deterministic tests. Each restart test uses a distinct temporary SQLite file and two service graphs.

~~~python
def test_completed_consequential_operation_is_skipped_after_restart(tmp_path):
    first_graph, first_tool = build_durable_graph(tmp_path / "completed.sqlite3")
    run = complete_consequential_step(first_graph)
    second_graph, second_tool = build_durable_graph(tmp_path / "completed.sqlite3")
    second_graph.resume(run.execution_id)
    assert first_tool.calls == ["write"]
    assert second_tool.calls == []


def test_known_safe_retry_reuses_operation_identity_and_increments_attempt(tmp_path):
    graph, tool = build_durable_graph(tmp_path / "retry.sqlite3", tool=proven_preinvoke_failure_tool())
    run = start_retryable_objective(graph)
    original_operation_id = load_run(graph, run.execution_id).steps[0].operation_id
    graph.resume(run.execution_id)
    loaded = load_run(graph, run.execution_id)
    assert loaded.steps[0].attempt_count == 2
    assert loaded.steps[0].operation_id == original_operation_id


def test_post_intent_exception_requires_recovery_and_never_retries(tmp_path):
    first_graph, first_tool = build_durable_graph(tmp_path / "uncertain.sqlite3", tool=ambiguous_exception_tool())
    run = start_consequential_objective(first_graph)
    second_graph, second_tool = build_durable_graph(tmp_path / "uncertain.sqlite3", tool=ambiguous_exception_tool())
    response = second_graph.resume(run.execution_id)
    assert load_run(second_graph, run.execution_id).status is ExecutionRunStatus.RECOVERY_REQUIRED
    assert second_tool.calls == []
    assert "uncertain" in response.response.lower()


async def test_concurrent_resume_claims_one_operation_and_calls_tool_once(tmp_path):
    graph, tool = build_durable_graph(tmp_path / "resume-race.sqlite3")
    run = start_claimable_consequential_objective(graph)
    first, second = await asyncio.gather(graph.resume(run.execution_id), graph.resume(run.execution_id))
    assert tool.calls == ["write"]
    assert sum(response.status is ExecutionRunStatus.COMPLETED for response in (first, second)) <= 1


async def test_concurrent_approval_claims_one_operation_and_calls_tool_once(tmp_path):
    graph, tool = build_durable_graph(tmp_path / "approval-race.sqlite3")
    run = start_approval_required_objective(graph)
    approval = inspect_pending(graph, run.execution_id)
    await asyncio.gather(
        graph.approve(run.execution_id, approval.approval_id),
        graph.approve(run.execution_id, approval.approval_id),
    )
    assert tool.calls == [{"path": "out.txt", "content": "approved"}]


def test_rejection_after_restart_has_zero_side_effect(tmp_path):
    first_graph, _ = build_durable_graph(tmp_path / "rejected.sqlite3")
    run = start_approval_required_objective(first_graph)
    second_graph, tool = build_durable_graph(tmp_path / "rejected.sqlite3")
    approval = inspect_pending(second_graph, run.execution_id)
    second_graph.reject(run.execution_id, approval.approval_id)
    assert tool.calls == []
    assert load_run(second_graph, run.execution_id).steps[0].status is DurableStepStatus.REJECTED


~~~

Payload immutability is directly enforced by Task 7's repository/service test. Explicit execution identity is exercised through Task 9's HTTP test, which targets one execution id with a different run's approval id and expects HTTP 409 with zero tool calls.

- [ ] **Step 2: Run tests to verify they fail**

Run: cd apps/backend; python -m pytest tests/api/test_durable_execution_e2e.py -v

Expected: FAIL until Tasks 1-9 supply persistence, claims, recovery, and active wiring.

- [ ] **Step 3: Keep this task test-only unless a named prior task has an identified gap**

Expected production-file changes for this task are none. If a mission test exposes a defect, add a focused failing assertion to the responsible Task 1-9 test file and correct only that task's named production file before returning here. Do not add integrations, a scheduler, conversation persistence, raw SQL in services, or live LLM dependencies.

- [ ] **Step 4: Run complete deterministic verification and fake-mode runtime check**

Run:

~~~powershell
cd apps/backend
$env:PATH = (Resolve-Path .\.venv313\Scripts).Path + ";" + $env:PATH
python -m compileall src
python -m pytest tests -v
$env:LLM_FAKE_MODE = "1"
uvicorn src.main:app --host 127.0.0.1 --port 8000
~~~

From a separate terminal verify GET /, start a deterministic multi-step objective, construct a fresh app/service graph against the same database, and resume by explicit execution id. Expected: completed work has no second call; uncertain consequential work is not auto-run; no live credential is read or printed.

- [ ] **Step 5: Commit checkpoint**

~~~bash
git add apps/backend/tests/api/test_durable_execution_e2e.py apps/backend/tests/api/test_chat_e2e.py
git commit -m "test: verify GARL durable execution recovery"
~~~

## Final Review Checklist

- [ ] Every legal durable transition has a repository conditional update.
- [ ] Every consequential tool call follows committed INTENT_RECORDED and occurs outside SQLite transactions.
- [ ] A post-intent exception defaults to uncertainty unless an adapter proves no side effect occurred.
- [ ] Concurrent approve/resume calls cannot claim or invoke the same operation twice.
- [ ] Approval validation uses persisted tool/action/canonical arguments, never LLM regeneration or conversation lookup.
- [ ] SQLite remains behind repository interfaces and has no shared global connection.
- [ ] Persisted JSON cannot include secret values or arbitrary object serialization.
- [ ] Restart tests use temporary files and fresh service graphs.
- [ ] Before merge, run git diff --check, backend compilation, full backend suite, fake-mode runtime exercise, frontend lint/build, and branch CI.
