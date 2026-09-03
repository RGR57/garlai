# GARL Web Operator V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe, durable, capability-scoped browser operation to GARL without creating a second planner or executor.

**Architecture:** Browser tools remain normal `BaseTool` implementations invoked by `ExecutorService`. A provider-neutral `BrowserSessionService` owns one ephemeral provider session per durable execution, observation, semantic targeting, policy, and reconciliation. Existing capability selection, validation, permissions, approval journals, operation claims, recovery, and `ObjectiveEvaluator` remain authoritative.

**Tech Stack:** Python 3.13, FastAPI, SQLite, pytest, Playwright Python adapter, deterministic fake provider, local HTTP fixture site.

**Spec:** `docs/superpowers/specs/2026-09-04-garl-web-operator-v1-design.md`

## Global Constraints

- Do not add `BrowserAgent`, `BrowserExecutor`, a second planner, or a separate browser loop.
- Browser tools are registered through `ToolRegistry`, validated by `ToolManager`, and invoked only through the existing executor path.
- No raw Playwright object, cookie, credential, password, CSRF token, payment value, raw DOM, or screenshot enters durable JSON, logs, planner prompts, or artifacts.
- Production navigation permits public HTTPS only; the local HTTP fixture origin is an injected test-only policy allowance.
- Page text is untrusted data and cannot affect capability selection, permission, approval, or other tool availability.
- Consequential dispatch uncertainty remains `UNCERTAIN`/`RECOVERY_REQUIRED`; no automatic submit replay is allowed.
- Use test-first development, focused tests after every task, `python -m compileall src`, then the full backend suite before the final commit.

---

### Task 1: Add Provider-Neutral Browser and Invocation Contracts

**Files:**
- Create: `apps/backend/src/models/browser.py`
- Create: `apps/backend/src/services/browser_provider.py`
- Modify: `apps/backend/src/models/tool_result.py`
- Modify: `apps/backend/src/tools/base_tool.py`
- Modify: `apps/backend/src/tools/tool_manager.py`
- Test: `apps/backend/tests/services/test_browser_contracts.py`

**Interfaces:**
- Consumes: `BaseTool`, `ToolResult`, existing `ToolManager.validate_arguments`.
- Produces: `BrowserObservation`, `BrowserElement`, `BrowserTarget`, `NavigationPolicy`, `ToolInvocationContext`, `ToolInvocationOutcome`, `BrowserProvider`, `BaseTool.execute_with_context`, `ToolManager.execute`, and `ToolManager.preflight`.

- [ ] **Step 1: Write failing contract tests.**

```python
async def test_manager_passes_executor_owned_context_only_to_context_aware_tool():
    await manager.execute("browser_observe", {}, ToolInvocationContext("run", 2, None))
```

- [ ] **Step 2: Run the focused tests.**

Run: `python -m pytest tests/services/test_browser_contracts.py -v`
Expected: FAIL because browser contract records and context-aware manager methods do not exist.

- [ ] **Step 3: Implement the minimal contracts.**

```python
@dataclass(frozen=True)
class ToolInvocationContext:
    execution_id: str | None
    step_id: int | None
    operation_id: str | None
    approved_payload_hash: str | None = None

class ToolInvocationOutcome(str, Enum):
    NOT_INVOKED = "not_invoked"
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"
```

Define JSON-only browser records with fixed length/count validators. Add `BaseTool.execute_with_context` as a backward-compatible default that calls `execute(**arguments)`. `ToolManager.execute` passes the context only through that method; `preflight` returns ready for legacy tools.

- [ ] **Step 4: Verify focused and existing manager tests.**

Run: `python -m pytest tests/services/test_browser_contracts.py tests/services/test_executor_service.py -v`
Expected: PASS; existing calculator/filesystem tools accept the default context path unchanged.

- [ ] **Step 5: Review and commit.**

Review that no provider object or secret-bearing field is serializable. Commit: `feat: add browser operation contracts`.

### Task 2: Build Navigation Policy and Browser Providers

**Files:**
- Create: `apps/backend/src/services/navigation_policy.py`
- Create: `apps/backend/src/services/fake_browser_provider.py`
- Create: `apps/backend/src/services/playwright_browser_provider.py`
- Modify: `apps/backend/requirements.txt`
- Modify: `apps/backend/src/core/config.py`
- Test: `apps/backend/tests/services/test_navigation_policy.py`
- Test: `apps/backend/tests/services/test_browser_provider.py`

**Interfaces:**
- Consumes: Task 1 `BrowserProvider`, `NavigationPolicy`, browser records.
- Produces: `ProductionNavigationPolicy`, test-only `LocalFixtureNavigationPolicy`, `FakeBrowserProvider`, `PlaywrightBrowserProvider`.

- [ ] **Step 1: Write failing policy and fake-provider tests.**

```python
@pytest.mark.parametrize("url", ["file:///x", "http://127.0.0.1", "https://169.254.169.254"])
def test_production_policy_rejects_unsafe_or_private_navigation(url):
    assert not policy.allows(url)

async def test_fake_provider_observes_a_frozen_accessibility_fixture():
    assert (await provider.observe(session)).elements[0].role == "button"
```

- [ ] **Step 2: Run the focused tests.**

Run: `python -m pytest tests/services/test_navigation_policy.py tests/services/test_browser_provider.py -v`
Expected: FAIL because no browser provider or navigation policy exists.

- [ ] **Step 3: Implement providers behind the protocol.**

Add `playwright` to backend requirements. The production policy accepts only normalized public `https` URLs, rejects embedded credentials and non-web schemes, and validates every document navigation/redirect. The test policy accepts only its exact dynamically supplied loopback origin. The Playwright adapter keeps all browser/page/context references private; the fake adapter uses frozen records and no network.

- [ ] **Step 4: Verify provider behavior.**

Run: `python -m pytest tests/services/test_navigation_policy.py tests/services/test_browser_provider.py -v`
Expected: PASS, including redirect rejection before a replacement document is loaded.

- [ ] **Step 5: Review and commit.**

Review that no production setting grants localhost/private-network access. Commit: `feat: add browser providers and navigation policy`.

### Task 3: Add BrowserSessionService and Durable Browser Facts

**Files:**
- Create: `apps/backend/src/services/browser_session_service.py`
- Modify: `apps/backend/src/repositories/durable_execution_repository.py`
- Modify: `apps/backend/src/repositories/sqlite_durable_execution_repository.py`
- Modify: `apps/backend/src/services/durable_execution_service.py`
- Test: `apps/backend/tests/services/test_browser_session_service.py`
- Test: `apps/backend/tests/repositories/test_sqlite_durable_execution_repository.py`

**Interfaces:**
- Consumes: Task 1 browser records, Task 2 provider/policy, `ExecutionRun.execution_context`.
- Produces: `BrowserSessionService.get_or_create`, `navigate`, `observe`, `resolve_target`, `record_browser_facts`, and generic repository context-patch operations.

- [ ] **Step 1: Write failing durability and isolation tests.**

```python
async def test_browser_session_is_keyed_by_execution_not_conversation():
    assert await service.get_or_create("run-a") != await service.get_or_create("run-b")

async def test_browser_context_patch_round_trips_only_sanitized_facts(repository):
    assert loaded.execution_context["browser"]["last_verified_url"] == "https://example.test/pricing"
```

- [ ] **Step 2: Run the focused tests.**

Run: `python -m pytest tests/services/test_browser_session_service.py tests/repositories/test_sqlite_durable_execution_repository.py -v`
Expected: FAIL because browser facts cannot be created or atomically persisted.

- [ ] **Step 3: Implement session ownership and context patching.**

```python
async def patch_execution_context(self, execution_id: str, patch: dict[str, JsonValue]) -> ExecutionRun: ...

async def observe(self, execution_id: str, invocation: ToolInvocationContext) -> BrowserObservation: ...
```

Generate a logical session ID once per execution, keep provider handles only in the service map, and add an optional `execution_context_patch` to durable step-outcome writes so browser facts merge in the same repository transaction as each outcome. `patch_execution_context` is reserved for session creation before the first action. Persist URL, sanitized observation/fingerprints, action facts, non-sensitive value hashes, and timestamps only.

- [ ] **Step 4: Verify session tests and durable regressions.**

Run: `python -m pytest tests/services/test_browser_session_service.py tests/services/test_recovery_service.py tests/repositories/test_sqlite_durable_execution_repository.py -v`
Expected: PASS; completed durable research and existing execution context remain unchanged.

- [ ] **Step 5: Review and commit.**

Review context JSON size limits and absence of cookies, values, DOM, and provider handles. Commit: `feat: persist browser session facts`.

### Task 4: Register Read-Oriented Browser Tools and Capability Scope

**Files:**
- Create: `apps/backend/src/tools/browser/browser_navigate_tool.py`
- Create: `apps/backend/src/tools/browser/browser_observe_tool.py`
- Modify: `apps/backend/src/tools/registry.py`
- Modify: `apps/backend/src/core/dependencies.py`
- Modify: `apps/backend/src/services/capability_registry.py`
- Modify: `apps/backend/src/services/permission_service.py`
- Test: `apps/backend/tests/tools/test_browser_navigate_tool.py`
- Test: `apps/backend/tests/tools/test_browser_observe_tool.py`
- Test: `apps/backend/tests/services/test_capability_registry.py`
- Test: `apps/backend/tests/services/test_capability_scoped_planning.py`

**Interfaces:**
- Consumes: Tasks 1-3 session service and invocation context; existing registry/resolver/catalog/validator.
- Produces: registered `browser_navigate`, `browser_observe`, and available `web_operation` capability.

- [ ] **Step 1: Write failing registration, schema, and scope tests.**

```python
def test_web_operation_only_selection_exposes_navigate_and_observe():
    assert selection.eligible_tool_names == ("browser_navigate", "browser_observe", "browser_select", "browser_fill", "browser_submit")

async def test_observe_returns_bounded_untrusted_browser_observation():
    assert result.output["trust"] == "untrusted_external_page_data"
```

- [ ] **Step 2: Run the focused tests.**

Run: `python -m pytest tests/tools/test_browser_navigate_tool.py tests/tools/test_browser_observe_tool.py tests/services/test_capability_registry.py tests/services/test_capability_scoped_planning.py -v`
Expected: FAIL because the tools and `web_operation` capability are absent.

- [ ] **Step 3: Implement normal read tools.**

Use explicit schemas: navigate accepts one `url`; observe accepts no planner-controlled session field. Both require a durable invocation identity, delegate to `BrowserSessionService`, and return constrained JSON. Register dependencies from one provider/session service and give both tools low-risk `READ_ONLY_POLICY` permission cases.

- [ ] **Step 4: Verify scope and existing research behavior.**

Run: `python -m pytest tests/tools/test_browser_navigate_tool.py tests/tools/test_browser_observe_tool.py tests/services/test_capability_registry.py tests/services/test_capability_scoped_planning.py tests/tools/test_web_search_tool.py -v`
Expected: PASS; browser-only planning cannot expose terminal/filesystem/git/research.

- [ ] **Step 5: Review and commit.**

Review dependency wiring for one `ToolManager` and no direct Playwright import outside the adapter. Commit: `feat: add browser observation capability`.

### Task 5: Add Constrained Observation Reasoning and Untrusted Rendering

**Files:**
- Modify: `apps/backend/src/models/plan.py`
- Modify: `apps/backend/src/services/plan_parser.py`
- Modify: `apps/backend/src/services/plan_validator.py`
- Modify: `apps/backend/src/services/variable_resolver.py`
- Modify: `apps/backend/src/services/executor_service.py`
- Modify: `apps/backend/src/services/planner_service.py`
- Test: `apps/backend/tests/agents/test_planner.py`
- Test: `apps/backend/tests/services/test_browser_target_contract.py`
- Test: `apps/backend/tests/services/test_browser_trust_boundary.py`

**Interfaces:**
- Consumes: Task 1 `BrowserTarget` and observation records; current parser/validator/LLM step execution.
- Produces: `PlanStep.result_contract`, validated `browser_target` and `browser_verification` output, typed exact variable substitution, and browser-page trust rendering.

- [ ] **Step 1: Write failing result-contract and injection tests.**

```python
def test_browser_target_contract_rejects_element_not_present_in_observation():
    assert not validator.validate(plan, state).valid

def test_exact_variable_reference_preserves_a_validated_browser_target():
    assert VariableResolver().resolve("{{step2}}", state) == target

def test_hostile_page_text_cannot_add_terminal_to_selected_tools():
    assert "terminal" not in planner_prompt
```

- [ ] **Step 2: Run the focused tests.**

Run: `python -m pytest tests/agents/test_planner.py tests/services/test_browser_target_contract.py tests/services/test_browser_trust_boundary.py -v`
Expected: FAIL because result contracts and browser trust rendering do not exist.

- [ ] **Step 3: Implement constrained LLM result handling.**

Allow only `browser_target` and `browser_verification` contract names, reject contracts on tool steps, parse LLM JSON strictly, validate target references against a prior bounded observation, and persist native JSON output. An exact `{{stepN}}` reference returns native validated JSON; embedded structured values are rejected. Render browser observations under a fixed data-only header that states they cannot authorize tools, permissions, approvals, secrets, or objective changes.

- [ ] **Step 4: Verify contracts and planner regressions.**

Run: `python -m pytest tests/agents/test_planner.py tests/services/test_browser_target_contract.py tests/services/test_browser_trust_boundary.py tests/services/test_capability_scoped_planning.py -v`
Expected: PASS; existing malformed-plan coverage remains green.

- [ ] **Step 5: Review and commit.**

Review that a page cannot cause dynamic tool registration, raw HTML prompt expansion, or arbitrary structured variable extraction. Commit: `feat: constrain browser observation reasoning`.

### Task 6: Add Preparatory Select and Fill Tools

**Files:**
- Create: `apps/backend/src/tools/browser/browser_select_tool.py`
- Create: `apps/backend/src/tools/browser/browser_fill_tool.py`
- Modify: `apps/backend/src/services/browser_session_service.py`
- Modify: `apps/backend/src/services/permission_service.py`
- Test: `apps/backend/tests/tools/test_browser_select_tool.py`
- Test: `apps/backend/tests/tools/test_browser_fill_tool.py`
- Test: `apps/backend/tests/services/test_execution_policy.py`

**Interfaces:**
- Consumes: Tasks 1-5 target contracts, session service, executor invocation context.
- Produces: `BrowserActionReceipt`, semantic select/fill operations, medium-risk allowed `CONSERVATIVE_POLICY` cases.

- [ ] **Step 1: Write failing preparation and sensitive-field tests.**

```python
async def test_fill_records_a_receipt_but_not_the_literal_value():
    assert "Ada Test" not in result.output["browser_facts"]

async def test_fill_rejects_password_like_field_without_provider_dispatch():
    assert provider.fill_calls == 0
```

- [ ] **Step 2: Run the focused tests.**

Run: `python -m pytest tests/tools/test_browser_select_tool.py tests/tools/test_browser_fill_tool.py tests/services/test_execution_policy.py -v`
Expected: FAIL because select/fill tools and browser permission cases are absent.

- [ ] **Step 3: Implement semantic preparation.**

Require a complete `BrowserTarget`; resolve it to exactly one live element and perform the action through the session service. Fill permits a literal only for a provider-declared non-sensitive field or an opaque `secret_ref`; it persists a field identifier and value hash, never a resolved secret/value. Both tools report `CONFIRMED` only for a provider-confirmed action and otherwise preserve conservative uncertainty behavior.

- [ ] **Step 4: Verify durable preparation behavior.**

Run: `python -m pytest tests/tools/test_browser_select_tool.py tests/tools/test_browser_fill_tool.py tests/services/test_durable_executor_service.py tests/services/test_execution_policy.py -v`
Expected: PASS; a process loss after a preparatory dispatch cannot cause automatic replay.

- [ ] **Step 5: Review and commit.**

Review that preparation is allowed but remains consequential in the durable journal. Commit: `feat: add browser preparation tools`.

### Task 7: Freeze and Preflight Exact Browser Commit Actions

**Files:**
- Create: `apps/backend/src/tools/browser/browser_submit_tool.py`
- Modify: `apps/backend/src/models/durable_execution.py`
- Modify: `apps/backend/src/repositories/durable_execution_repository.py`
- Modify: `apps/backend/src/repositories/sqlite_durable_execution_repository.py`
- Modify: `apps/backend/src/services/approval_service.py`
- Modify: `apps/backend/src/services/executor_service.py`
- Modify: `apps/backend/src/services/permission_service.py`
- Test: `apps/backend/tests/services/test_browser_approval.py`
- Test: `apps/backend/tests/services/test_durable_approval_service.py`

**Interfaces:**
- Consumes: Tasks 1, 3, and 6 action receipts and semantic targets; existing immutable `ApprovalRequest` and operation journal.
- Produces: `ApprovalEventType.INVALIDATED`, repository `invalidate_approval`, commit preflight, `browser_submit` high-risk approval policy, and outcome-aware executor recording.

- [ ] **Step 1: Write failing exact-target approval tests.**

```python
async def test_approved_submit_does_not_click_when_live_target_fingerprint_changed():
    assert provider.submit_calls == 0
    assert run.status is ExecutionRunStatus.RECOVERY_REQUIRED

async def test_approved_submit_claims_and_dispatches_exact_target_once():
    assert provider.submit_calls == 1
```

- [ ] **Step 2: Run the focused tests.**

Run: `python -m pytest tests/services/test_browser_approval.py tests/services/test_durable_approval_service.py -v`
Expected: FAIL because browser submit has no approval freeze or preflight invalidation.

- [ ] **Step 3: Implement frozen commit semantics.**

`browser_submit` accepts only a `BrowserTarget` and non-sensitive expected-state facts. `PermissionService` always requires high-risk approval. After approval and before operation claim, `ToolManager.preflight` reobserves the current page and validates origin/path, target uniqueness, selected preparation facts, and commit fingerprint. `invalidate_approval` appends an immutable journal event and moves the run to recovery when no click was dispatched. The executor records `KNOWN_FAILED` only for a proven `NOT_INVOKED` outcome; unproven results remain uncertain.

- [ ] **Step 4: Verify approval, claim, and legacy approval suites.**

Run: `python -m pytest tests/services/test_browser_approval.py tests/services/test_durable_approval_service.py tests/services/test_approval_service.py tests/repositories/test_operation_claims.py -v`
Expected: PASS; payload mutation and cross-run approval remain rejected.

- [ ] **Step 5: Review and commit.**

Review that approval binds session/logical target facts rather than "the current button" and that preflight happens before dispatch. Commit: `feat: gate browser commits with exact approval`.

### Task 8: Reconcile Browser State During Durable Recovery

**Files:**
- Create: `apps/backend/src/services/execution_reconciler.py`
- Modify: `apps/backend/src/services/browser_session_service.py`
- Modify: `apps/backend/src/services/recovery_service.py`
- Modify: `apps/backend/src/services/durable_execution_service.py`
- Modify: `apps/backend/src/core/dependencies.py`
- Test: `apps/backend/tests/services/test_browser_recovery.py`
- Test: `apps/backend/tests/services/test_recovery_service.py`

**Interfaces:**
- Consumes: Task 3 durable browser facts and Task 7 operation outcomes.
- Produces: `ExecutionReconciler.reconcile(run, orphaned_operations)`, browser reconciliation result, recovered `RECOVERY_REQUIRED` facts, and dependency registration.

- [ ] **Step 1: Write failing restart and orphaned-submit tests.**

```python
async def test_fresh_service_reconciles_prepared_state_without_refilling():
    assert provider_after_restart.fill_calls == 0

async def test_orphaned_submit_with_no_visible_success_becomes_recovery_required():
    assert provider_after_restart.submit_calls == 0
```

- [ ] **Step 2: Run the focused tests.**

Run: `python -m pytest tests/services/test_browser_recovery.py tests/services/test_recovery_service.py -v`
Expected: FAIL because recovery has no browser reconciler.

- [ ] **Step 3: Implement observation-first reconciliation.**

Add a narrow reconciler protocol injected into `RecoveryService`. On a browser run, create a fresh provider session, navigate only to the last verified allowed URL, observe, compare durable semantic facts, and atomically save the new observation. Never replay select/fill/submit. For an orphaned submit, record completion only when observable success proves the operation; otherwise invoke the existing uncertain transition. Material prepared-state mismatch becomes actionable recovery required.

- [ ] **Step 4: Verify recovery and durable regression suites.**

Run: `python -m pytest tests/services/test_browser_recovery.py tests/services/test_recovery_service.py tests/services/test_durable_executor_service.py tests/api/test_durable_execution_e2e.py -v`
Expected: PASS; non-browser runs preserve current recovery behavior.

- [ ] **Step 5: Review and commit.**

Review that reconciliation only observes and compares external reality before continuation. Commit: `feat: reconcile durable browser executions`.

### Task 9: Add Deterministic Local Playwright Marketplace Fixture

**Files:**
- Create: `apps/backend/tests/browser_fixture_site.py`
- Create: `apps/backend/tests/conftest.py`
- Create: `apps/backend/tests/integration/test_playwright_browser_provider.py`
- Modify: `apps/backend/requirements.txt`
- Test: `apps/backend/tests/integration/test_playwright_browser_provider.py`

**Interfaces:**
- Consumes: Task 2 Playwright adapter and test-only navigation policy.
- Produces: `local_marketplace` fixture with mutable plans, explicit review/confirmation pages, and a scoped loopback origin.

- [ ] **Step 1: Write failing real-browser integration tests.**

```python
async def test_playwright_provider_observes_semantic_plan_cards(local_marketplace):
    assert {element.accessible_name for element in observation.elements} >= {"Choose Starter", "Choose Pro"}

async def test_fixture_records_commit_only_after_submit(local_marketplace):
    assert await local_marketplace.commit_count() == 1
```

- [ ] **Step 2: Run the focused integration tests.**

Run: `python -m pytest tests/integration/test_playwright_browser_provider.py -v`
Expected: FAIL because the local site fixture and adapter integration are absent.

- [ ] **Step 3: Implement deterministic test infrastructure.**

Create a loopback-only in-process HTTP app with fixture-supplied plan facts and server-side test-session state. It renders accessible plan buttons, labelled non-sensitive test fields, a review page, one final confirmation button, and a confirmation page. It has no product-specific import outside tests. Install the browser binary through documented test setup only, never at application startup.

- [ ] **Step 4: Verify the real local browser path.**

Run: `python -m pytest tests/integration/test_playwright_browser_provider.py -v`
Expected: PASS with no public network access.

- [ ] **Step 5: Review and commit.**

Review that fixture-local HTTP allowance cannot be enabled by production configuration. Commit: `test: add deterministic browser marketplace fixture`.

### Task 10: Extend Objective Evaluation and Prove the Full Mission

**Files:**
- Modify: `apps/backend/src/services/objective_evaluator.py`
- Modify: `apps/backend/src/services/cognitive_pipeline.py`
- Create: `apps/backend/tests/services/test_web_operator_mission.py`
- Modify: `apps/backend/tests/services/test_objective_evaluator.py`
- Modify: `apps/backend/tests/api/test_chat_e2e.py`

**Interfaces:**
- Consumes: Tasks 4-9 browser facts, approval events, operation outcomes, constrained verification output.
- Produces: browser-aware evidence extraction inside the existing `ObjectiveEvaluator` and full durable mission evidence.

- [ ] **Step 1: Write failing mission tests with changed plan prices.**

```python
async def test_mission_selects_current_cheapest_qualifying_observed_plan(fixture):
    assert fixture.selected_plan == "Pro"

async def test_mission_waits_for_approval_then_confirms_once(fixture):
    assert fixture.commit_count == 1
```

Add variants for rejection, fresh-service restart after preparation, visible-success orphan reconciliation, and ambiguous orphan recovery required.

- [ ] **Step 2: Run the focused mission tests.**

Run: `python -m pytest tests/services/test_web_operator_mission.py tests/services/test_objective_evaluator.py -v`
Expected: FAIL because browser facts do not count as observable objective evidence.

- [ ] **Step 3: Implement only evaluator evidence extraction.**

Keep one `ObjectiveEvaluator`. It requires the selected observed plan to satisfy constraints, a prepared receipt, an approval journal fact before submit, exactly one confirmed commit operation, and a validated success observation when the objective calls for completion. It does not trust a raw page string or an LLM assertion without referenced observation evidence.

- [ ] **Step 4: Verify mission, API, and capability regression tests.**

Run: `python -m pytest tests/services/test_web_operator_mission.py tests/services/test_objective_evaluator.py tests/api/test_chat_e2e.py tests/services/test_capability_fabric_mission.py -v`
Expected: PASS; price changes select the correct currently observed plan rather than a canned plan.

- [ ] **Step 5: Review and commit.**

Review that success is based on observed external state and not HTTP success or step count. Commit: `test: verify durable web operator mission`.

### Task 11: Run Whole-System Gates and Perform Final Review

**Files:**
- Modify only if a failed gate exposes an in-scope defect in a preceding task.
- Test: all backend tests and actual deterministic API runtime.

**Interfaces:**
- Consumes: the complete V1 implementation.
- Produces: verified branch evidence, no behavior beyond the spec.

- [ ] **Step 1: Run compilation and the full backend suite.**

Run: `python -m compileall src` and `python -m pytest tests -v` from `apps/backend`.
Expected: PASS, with live credential tests skipped and local browser tests self-contained.

- [ ] **Step 2: Run a deterministic Uvicorn smoke.**

Run Uvicorn without reload using fake LLM/research/browser configuration and a disposable durable SQLite path. Exercise `GET /`, then `POST /api/v1/chat` through the approved local marketplace mission until the pending approval response, approval resume, and completed response are observed.
Expected: browser session IDs are execution-bound, final submit occurs once, and no secret is printed.

- [ ] **Step 3: Run frontend gates without changing the frontend.**

Run: `npm ci`, `npm run lint`, and `npm run build` from `apps/frontend` when npm is available.
Expected: PASS, or report the local environment blocker without treating it as a GARL code result.

- [ ] **Step 4: Review the final diff.**

Run: `git diff --check`, `git status --short`, `git diff --stat main...HEAD`, and inspect every changed file. Confirm there is no browser executor/agent, direct Playwright dependency outside the adapter, secret persistence, selector-only tool, global catalog leak, local-network production bypass, payment behavior, CAPTCHA behavior, or blind consequential replay.

- [ ] **Step 5: Commit only green, reviewed changes.**

Commit: `feat: add durable GARL web operator`. Do not merge, force-push, or delete the branch.
