# GARL Core V1 Durable Execution Design

## 1. GARL North-Star Context

GARL is a domain-independent autonomous work-execution platform. A user gives GARL an objective; GARL understands it, creates and validates a plan, executes permitted work, observes results, recovers safely, requests approval for consequential actions, and returns a useful outcome. Durable Execution V1 strengthens that path across process and application reconstruction. It does not add a domain-specific capability or turn GARL into a website builder.

## 2. Problem Statement

The active runtime keeps execution truth in Python objects. A process restart loses the objective, selected plan, step history, variables, pending approval, and evidence of whether a tool was called. The most dangerous crash window is after an external side effect begins but before GARL records its outcome: current code cannot distinguish that case from a step that never started and can therefore repeat work after reconstruction.

V1 must preserve enough execution-scoped state to continue a single objective safely. It must skip completed work, retain pending approvals, retain the exact approved payload, record a stable operation identity before a consequential side effect, and stop for human intervention when the side effect outcome is ambiguous.

## 3. Current State Ownership Architecture

The mounted request path is `POST /api/v1/chat` in `src/api/v1/chat.py`, then `ConversationService.chat`, `AgentService.respond`, `CognitivePipeline.run`, `ExecutorService.execute`, `ReviewerService.review`, and `ResponseComposer.compose`.

`AgentService.respond` obtains a `CognitiveState` from `CognitiveStateRepository.get_or_create(conversation_id)`. `CognitiveState` owns `ExecutionState`, reasoning, execution trace, objective, execution-scoped memories and knowledge context, notes, artifacts, final response, iteration, and confidence. `ExecutionState` owns `current_step`, `attempt`, variables, `history: list[StepResult]`, and the pending approval fields. `StepResult` contains step id, success, output/error, tool/action, artifact, and metadata.

`CognitivePipeline.run` regenerates and validates a plan on every cognitive iteration, calls `ExecutionState.begin_attempt`, and passes the full selected `ExecutionPlan` to `ExecutorService.execute`. The executor loops every plan step, resolves variables, checks arguments and permissions, invokes a tool or LLM, appends one `StepResult`, then stores successful output in `variables`. `ApprovalService` later executes the exact pending tool and arguments in `ExecutionState`; it appends a result and approval record, then clears approval state. `DecisionService` chooses return, retry, replan, or wait for approval from the last in-memory result.

`ConversationService` stores messages before and after calling the agent. The conversation id is a request-routing value, not a durable run identity.

## 4. Current Persistence Gaps

`CognitiveStateRepository` is a dictionary keyed by conversation id. `InMemoryConversationRepository` and `InMemoryMemoryRepository` are also process-local dictionaries. Dependency factories cache these objects only for the current process. `src/core/lifespan.py` only configures logging; it has no database initialization or recovery integration. No active code uses SQLite, a database, operation identity, idempotency key, or durable plan storage.

The state repository interface is synchronous and concrete rather than an abstract durable-run contract. The conversation and memory repository interfaces are suitable patterns to follow, but they are explicitly outside this milestone's persistence boundary. There is no reusable persistence mechanism to adopt.

## 5. Crash-Window Analysis

| Case | Current behavior | V1 behavior |
| --- | --- | --- |
| A. Step not started, process dies | No durable evidence; plan is lost. | Persisted `PENDING` step has no intent record and may be considered for safe execution according to policy. |
| B. Step marked executing, process dies before side effect | Current state is lost. | A consequential operation is claimed by recording `INTENT_RECORDED`; after restart it is not assumed safe merely because no completion exists. |
| C. Side effect occurs, process dies before success persistence | GARL cannot tell whether it happened. | Operation becomes `UNCERTAIN`; run becomes `RECOVERY_REQUIRED`; automatic retry is prohibited. |
| D. Approval requested, process dies | Pending tool and arguments are lost. | Persisted approval request remains `PENDING`; the tool has not executed. |
| E. Approval/resume races or process dies around execution | Two callers may execute, or state is lost. | Approval and operation have explicit identities; an atomic claim permits at most one caller to cross the side-effect boundary. |

For consequential work, an exception after the external invocation begins is not proof that the side effect did not occur. It is `UNCERTAIN` unless a tool adapter positively establishes a known pre-side-effect failure.

## 6. Persistence Options and Recommendation

### SQLite aggregate plus journal: recommended

Use standard-library `sqlite3` behind a durable execution repository. Maintain a compact current execution aggregate for recovery and append-only operation and approval journals for safety and auditability. SQLite gives local durability, short transactional state transitions, deterministic temporary-file tests, and a low-complexity migration path to PostgreSQL through the repository contract.

### File/JSON state persistence: rejected

Atomic conditional claims, foreign keys, concurrent request handling, schema migration, and append-only operation facts become fragile or hand-built. A JSON file can preserve snapshots but does not provide the required transactional safety around concurrent approval/resume requests.

### External PostgreSQL now: rejected

PostgreSQL would improve multi-node concurrency but requires infrastructure, deployment operations, and environment configuration that V1 does not need. GARL Core V1 is single-node and limited-concurrency. The interface, not premature infrastructure, is the migration boundary.

## 7. Durable Execution Aggregate

The durable aggregate is an execution run, not a persisted conversation. `execution_id` is authoritative for state-changing operations. `conversation_id` is nullable routing/context metadata and is never used to select an arbitrary active execution.

`execution_runs` stores:

- `execution_id`, original objective, optional conversation id, status, plan version, current step id, next step id, retry/iteration metadata, final response, execution-scoped context JSON, variables JSON, timestamps, and non-secret metadata.
- The execution-scoped context contains only information required to execute remaining plan steps, including canonical plan input and any bounded messages required by an LLM-only remaining step. It is not a replacement for general conversation history.

`execution_steps` stores one row per persisted plan step: execution id, stable plan step id and ordinal, action, tool, canonical input and arguments, resolved arguments once prepared, execution classification, status, logical operation id when applicable, attempt count, result/error metadata, artifact reference, and timestamps. Step results and artifact references are constrained JSON DTOs validated on load.

The existing `CognitiveState` and `ExecutionState` remain runtime views assembled from this aggregate. They stop being the only resumable source of truth.

## 8. Legal State Machines

An explicit `PLANNING` run state is required because a durable record can exist before a plan is validated. `CANCELLED` and `SKIPPED` are not introduced in V1 because current active behavior has no cancellation flow and skipped work is represented by completed predecessor state plus the resume cursor.

Run states are `PLANNING`, `RUNNING`, `WAITING_APPROVAL`, `RECOVERY_REQUIRED`, `COMPLETED`, and `FAILED`. Step states are `PENDING`, `EXECUTING`, `COMPLETED`, `KNOWN_FAILED`, `WAITING_APPROVAL`, `REJECTED`, and `UNCERTAIN`.

### Run transitions

| From | To | Trigger |
| --- | --- | --- |
| `PLANNING` | `RUNNING` | A validated plan and step rows persist atomically. |
| `RUNNING` | `WAITING_APPROVAL` | A step requires approval and its exact approval request persists. |
| `WAITING_APPROVAL` | `RUNNING` | The exact pending approval is approved; no tool executes in this transition. |
| `WAITING_APPROVAL` | `FAILED` | The exact pending approval is rejected and no remaining active work can complete the objective. |
| `RUNNING` | `COMPLETED` | All required steps have durable successful outcomes and response composition completes. |
| `RUNNING` | `FAILED` | A terminal failure or denied action ends the objective. |
| `RUNNING` | `RECOVERY_REQUIRED` | A consequential operation becomes uncertain. |
| `RECOVERY_REQUIRED` | `RUNNING` | A future explicit reconciliation or authorized human resolution records a safe outcome. |

### Step transitions

| From | To | Trigger |
| --- | --- | --- |
| `PENDING` | `WAITING_APPROVAL` | Permission policy requires approval; exact payload is frozen. |
| `PENDING` | `EXECUTING` | Atomic claim succeeds. For consequential work this also appends `INTENT_RECORDED`. |
| `WAITING_APPROVAL` | `PENDING` | Exact approval is granted; operation identity and canonical payload are unchanged. |
| `WAITING_APPROVAL` | `REJECTED` | The user rejects the frozen action; no tool invocation occurs. |
| `WAITING_APPROVAL` | `KNOWN_FAILED` | The frozen action cannot be revalidated before invocation. |
| `EXECUTING` | `COMPLETED` | Tool/LLM result is durably recorded as successful. |
| `EXECUTING` | `KNOWN_FAILED` | Adapter positively proves no consequential side effect occurred, or a pure/read-only step fails. |
| `EXECUTING` | `UNCERTAIN` | Consequential invocation began but no confirmed terminal outcome exists. |
| `KNOWN_FAILED` | `PENDING` | Policy permits a known-safe retry; attempt count increments. |

Repository methods enforce these transitions with conditional updates. Illegal transitions fail explicitly rather than mutating rows freely.

## 9. Repository and Storage Architecture

Introduce a domain-facing `DurableExecutionRepository` protocol in `src/repositories`. It accepts and returns GARL domain DTOs; it contains no SQLite types in its public contract. A `SQLiteDurableExecutionRepository` implementation owns schema initialization, connection use, SQL, transactions, serialization, and migration application.

The principal repository operations are:

- create planning run; persist validated plan and transition it to running;
- load an execution aggregate by `execution_id` and validate DTOs;
- list resumable/recovery-required executions without starting them;
- atomically request, approve, or reject one approval by `approval_id` and `execution_id`;
- atomically claim a step/operation by execution id, step id, and operation id;
- persist known result/failure, mark uncertain, and update the run cursor;
- persist terminal run outcome and append trace-safe journal facts.

`AgentService`, `CognitivePipeline`, `ExecutorService`, and `ApprovalService` depend on this interface or a thin domain checkpoint service that delegates to it. No runtime/domain service contains SQL. The repository records facts; `PermissionService` and tool execution policy classify risk and retry safety.

## 10. SQLite Connection, Schema, and Transaction Contract

The SQLite implementation creates a short-lived connection per repository operation or per explicitly bounded repository transaction. It never shares one unsafe mutable global connection across FastAPI requests. Every connection enables `PRAGMA foreign_keys = ON`, configures a bounded busy timeout, and enables WAL mode after confirming the local SQLite file supports it. WAL is appropriate for V1's limited concurrent readers and short writers; it does not make external tool execution transactional.

SQLite calls are synchronous. Async services call repository operations through a repository-owned `asyncio.to_thread` adapter so transaction work does not block the event loop. Connections are created and closed inside that worker execution. A process-local lock is not the correctness mechanism; SQLite conditional writes and unique constraints are.

Schema initialization runs from lifespan/configuration startup and is idempotent. A `schema_migrations` table records ordered versions. V1 has an initial migration and executes it in an exclusive short schema transaction. Deterministic tests create a new temporary database path for each test.

The tables are:

- `schema_migrations(version, applied_at)`;
- `execution_runs` and `execution_steps` for the compact aggregate;
- `operation_journal(operation_event_id, execution_id, step_id, operation_id, event_type, attempt_id, payload_hash, fact_json, occurred_at)`;
- `approval_journal(approval_event_id, approval_id, execution_id, step_id, operation_id, event_type, canonical_payload_json, payload_hash, occurred_at)`.

Unique constraints include `(execution_id, step_id)` for steps, unique `operation_id`, unique `approval_id`, and one `INTENT_RECORDED` event for an operation. Those constraints support the atomic claim contract.

## 11. Operation Journal and Atomic Claim

Every consequential operation receives a stable `operation_id` before it can be approved or invoked. It is derived/generated once for the logical execution step and persists across restart and known-safe retries. Each invocation has a separate `attempt_id` and attempt count.

For a consequential action, `claim_operation` is one SQLite transaction:

1. verify the requested `execution_id`, `step_id`, operation id, expected `PENDING` state, and canonical payload hash;
2. conditionally update the step from `PENDING` to `EXECUTING` only if no caller has claimed it;
3. append the unique `INTENT_RECORDED` journal fact with the operation id and attempt id;
4. advance the run cursor if applicable; commit.

Exactly one caller can commit that transition. A second concurrent approve/resume caller observes an already claimed operation and receives a non-executing outcome. It must not invoke the tool. The external call occurs only after the claim transaction commits and always outside an SQLite transaction.

After the call, a second short transaction writes the result, appends `COMPLETED` or a proven known-failure fact, updates the step/run aggregate, variables, and artifact references, then commits. If the invocation throws or the process dies after intent, V1 records `UNCERTAIN` whenever it has execution control; recovery converts orphaned `INTENT_RECORDED` operations to `UNCERTAIN` and the run to `RECOVERY_REQUIRED`.

## 12. Approval Persistence and Payload Immutability

An approval request is a persistent immutable authorization record. It contains `approval_id`, `execution_id`, `step_id`, `operation_id`, tool, action, canonical resolved arguments, risk/reason, payload hash, requested timestamp, and status facts.

Requesting approval transactionally stores the frozen payload and appends `REQUESTED`; the step and run transition to `WAITING_APPROVAL`. Approval uses all durable identities, not conversation id. Approve appends `APPROVED` only if the approval remains pending and the supplied/loaded payload hash matches the frozen canonical payload. Reject appends `REJECTED` under the same condition and performs no external call.

After approval, resume uses the persisted payload; it does not ask an LLM to regenerate a plan, tool, action, or arguments. A changed tool/action/arguments has a different payload hash, invalidates the old authorization, and requires a new approval record and operation transition. Multiple executions may share a conversation id; each approval and resume command must identify the target execution and approval explicitly.

## 13. Tool Policy and Idempotency Contract

V1 adds a small execution classification at the existing permission/tool boundary: read-only, consequential, and known-failure retry eligibility. The repository does not decide danger. Existing permission and risk evaluation remains authoritative; unknown tools remain denied.

The contract is deliberately limited:

1. A completed GARL step is never executed again during resume.
2. When a tool/provider supports an idempotency key, GARL supplies the stable `operation_id` and reuses it for the same logical operation.
3. Pure/read-only actions may retry according to policy.
4. A consequential action may retry only when the adapter proves failure before side effect.
5. A consequential action with an intent record and no confirmed terminal outcome is uncertain and cannot retry automatically.

This does not claim universal exactly-once delivery. It prevents GARL from issuing a second unproven consequential invocation and preserves enough evidence for reconciliation.

## 14. Recovery and Explicit Resume Algorithm

Startup initializes storage but does not schedule work. An explicit resume request targets `execution_id` and optional `approval_id`; it loads and validates the aggregate in a fresh service graph.

1. Reject missing, terminal, or identity-mismatched requests.
2. Rebuild an in-process execution view from the persisted run, plan, variables, completed step results, artifacts, and execution-scoped context.
3. For every nonterminal consequential operation with `INTENT_RECORDED` and no confirmed terminal outcome, transactionally append uncertainty, mark its step `UNCERTAIN`, and mark the run `RECOVERY_REQUIRED`.
4. If the run is waiting approval, return its frozen request without invoking a tool. An explicit approve/reject targets its approval id.
5. Skip completed steps; restore their outputs into variables.
6. Resume only the first legal pending step. A known-safe retry receives a new attempt id but the same logical operation id. Never regenerate the original plan because of restart.
7. Stop on `UNCERTAIN`, terminal failure, DENY, or a new approval requirement. Return a useful status/final response rather than pretending the objective completed.

Future tool-specific reconciliation may resolve an uncertain operation, but V1 provides the durable state and safe stop only; it does not invent a background scheduler or automatic reconciliation.

## 15. Dependency-Injection and Lifespan Integration

`Settings` gains a non-secret durable database path with a local default under ignored runtime storage. `core.dependencies` owns one configured repository factory and injects it into the durable run coordinator, pipeline/executor checkpoint boundary, approval service, and agent service. The repository factory does not expose a raw connection globally.

`lifespan` runs idempotent schema initialization and closes no shared application connection because repository operations own their connections. The active chat route is not restructured. V1 may extend request/response schemas with `execution_id`, `approval_id`, or resume identity fields while preserving the existing chat path and response compatibility as far as practical.

## 16. Migration and Compatibility

Existing in-memory `CognitiveStateRepository` supports current tests and legacy unmounted surfaces but is not the durable source for active V1 executions. The new durable run repository is introduced beside it and becomes the active runtime source through dependency wiring. Existing API callers that only send `conversation_id` and `message` can start a new execution; state-changing resume/approve/reject calls must return and accept explicit durable identities rather than selecting by conversation alone.

The schema migration version lets a future PostgreSQL implementation map the same aggregate and journal semantics. Old process-local states cannot be recovered after deployment because they were never durable; new runs begin with the durable contract. No legacy `src/agents` cleanup or API router restructuring is part of this migration.

## 17. Security and Data Constraints

Persist only constrained execution data required for resume. Do not persist API keys, provider credentials, authorization tokens, cookie values, raw secret values, or arbitrary Python objects. Store a secret reference/identifier only if a later secure secret-reference architecture exists.

Canonical JSON serialization is explicit for plan steps, arguments, output metadata, artifacts, and minimal execution context. It rejects unsupported values and validates deserialized DTOs before the runtime uses them. Payload hashes cover canonical tool/action/arguments for approval integrity. Logs and tests use synthetic values and must not print database secrets or provider credentials.

## 18. Testing Architecture and Acceptance Matrix

Tests use temporary SQLite files, deterministic fake LLMs, recording tools, and genuinely new repository/service graphs to simulate restart. Mandatory tests require no live LLM, network provider, or API key.

| Scenario | Evidence |
| --- | --- |
| Basic persistence | Fresh graph loads the same execution id, objective, plan, variables, and state. |
| Completed-step restart | Restart resumes only the remaining step; completed recording tool has one call. |
| Pending approval restart | Fresh graph finds frozen pending approval; tool has zero calls. |
| Approval after restart | Exact approved payload and stable operation id execute once. |
| Approval rejection after restart | Rejection persists; tool has zero calls. |
| Tool failure | Known failure remains failed after reconstruction and never appears successful. |
| Safe retry | Proven pre-side-effect retry increments attempt metadata and preserves logical operation id. |
| Completed consequential action | Completed journal outcome causes restart to skip the action. |
| Ambiguous side effect | Intent plus simulated crash/unknown exception produces `UNCERTAIN` and `RECOVERY_REQUIRED`, never a second call. |
| Multi-step objective | Fresh graph skips completed step(s) and executes only remaining legal steps. |
| Concurrent resume | Two callers race to claim one consequential operation; one claim succeeds and tool calls are at most one. |
| Concurrent approval | Two approval/resume callers cannot produce two side effects. |
| Post-intent exception | Invocation exception without proof of pre-side-effect failure becomes uncertain. |
| Approved payload immutability | Changed payload is rejected and needs a new approval. |
| Explicit execution identity | Two runs with one conversation id cannot approve/resume each other. |
| Mission-level restart | A general multi-step digital-work objective survives fresh application/service reconstruction and completes without repeating work. |

## 19. Explicit Non-Goals

This milestone does not add general conversation persistence, long-term memory persistence, profile/preferences, vector/retrieval persistence, browser automation, additional integrations, website/app-building features, distributed workers, queues, background scheduling, PostgreSQL, Redis, an ORM, full event sourcing, structured API error envelopes, legacy `src/agents` cleanup, or API router restructuring.

## 20. Acceptance Criteria

GARL can own one objective across process/application reconstruction. It durably preserves the objective, validated plan, current/next step, completed outputs, variables required by later steps, artifacts, pending approval, operation identity, and safety-relevant history. It never reruns a completed step, never runs a rejected action, permits only one concurrent caller to claim a consequential operation, and stops in recovery-required state whenever a consequential outcome is ambiguous. The complete backend suite and deterministic restart E2E suite pass without live provider credentials.

## 21. Risks and Mitigations

- SQLite is single-node and has limited writer concurrency. Short transactions, WAL, busy timeout, conditional claims, and repository abstraction are appropriate V1 mitigations; multi-node deployment is deferred.
- Some existing tools cannot prove pre-side-effect failure. The default is uncertainty, not retry.
- Persisted JSON can drift from Python models. Explicit DTO codecs, schema versioning, and validation on load limit corruption and migration risk.
- Existing pipeline regenerates plans each iteration. V1 must introduce a persisted-plan continuation boundary carefully, with regression coverage for retry/replan behavior.
- Database writes add synchronous work. Repository-owned worker-thread calls keep event-loop blocking bounded.
- An explicit resume API needs identity-bearing request semantics. Adding identities without a broad API error redesign keeps scope constrained.
