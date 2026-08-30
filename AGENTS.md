# GARL Engineering Constitution

## Mission

GARL is an autonomous work-execution platform.

The intended product experience is:

User gives GARL an objective
? GARL understands the objective
? constructs a valid plan
? executes real work through tools
? maintains explicit execution state
? observes results
? recovers from failures
? requests human approval for consequential actions
? continues execution
? returns a useful completed result.

The goal is NOT merely to build a chatbot or a collection of AI features.

## Primary Engineering Objective

Move GARL toward reliable autonomous execution while preserving:

- correctness
- safety
- explicit state
- recoverability
- auditability
- permission boundaries
- useful final outcomes

Reliability takes priority over adding more tools or flashy features.

## Core Runtime

Treat these areas as critical system contracts:

- Planner
- ExecutionPlan / PlanStep
- PlanParser
- PlanValidator
- DecisionService
- ExecutionState
- ExecutorService
- ToolManager
- ToolRegistry / ToolRouter
- PermissionService
- ApprovalService
- ResponseComposer
- Memory / Cognitive pipeline
- API boundaries

Do not casually bypass these layers.

## Engineering Rules

1. LLM output is untrusted input.
2. Validate before execution.
3. Do not solve schema failures only with prompt changes.
4. Tool names and arguments must be validated.
5. Unknown tools must fail safely.
6. External side effects must be permission-aware.
7. Retries must not accidentally duplicate consequential actions.
8. Execution state must remain recoverable.
9. A local bug fix must not violate another runtime contract.
10. Do not hide failures with broad exception handling.
11. Prefer root-cause fixes over patches.
12. Do not replace GARL architecture with a framework unless there is a demonstrated architectural reason.
13. Existing behaviour must not regress when new capability is added.
14. Passing unit tests alone does not mean GARL works.
15. Evaluate whether the user's real objective was successfully completed.

## Development Loop

For every significant task:

1. inspect relevant architecture and callers
2. reproduce the problem
3. establish expected behaviour
4. add or update a regression test when appropriate
5. make the smallest architecturally correct change
6. compile
7. run relevant tests
8. run the wider test suite
9. start relevant services when required
10. exercise real integration behaviour
11. inspect failures and logs
12. repeat until verified
13. review the final diff
14. report remaining risks

Never claim success without verification evidence.

## Backend

Working directory:

apps/backend

Minimum validation:

python -m compileall src
python -m pytest tests -v

When runtime behaviour is involved, start the FastAPI application and test the relevant API path rather than relying only on imports.

Do not use unrestricted Uvicorn reload on this Windows project because watching the virtual environment can exhaust resources.

For local development use:

uvicorn src.main:app --reload --reload-dir src

or for debugging:

uvicorn src.main:app

## Frontend

Working directory:

apps/frontend

Minimum validation:

npm ci
npm run lint
npm run build

If UI behaviour changes, inspect the rendered application rather than relying only on compilation.

## Required GARL Behaviour Tests

Maintain coverage for:

### Planner / Parser
- valid plan
- JSON in Markdown fences
- malformed JSON
- empty steps
- JSON null tool
- textual "null" tool
- textual "none" tool
- unknown tool
- malformed arguments

### Execution
- conversational/no-tool request
- one successful tool step
- multiple dependent steps
- tool failure
- partial failure
- retry
- timeout
- interrupted execution
- resume

### Permissions
- safe action
- approval-required action
- approval accepted
- approval rejected
- resumed execution after approval

### State
- success
- failure
- paused
- resumed
- no duplicate execution

### End-to-End
- conversation-only objective
- tool objective
- multi-tool objective
- malformed planner output
- denied action
- failed tool
- recovery path

## Mission-Level Evaluation

Do not mark a run successful merely because:

- HTTP returned 200
- Python did not crash
- tools executed
- unit tests passed

Also determine:

- Did GARL understand the objective?
- Was the plan appropriate?
- Were the correct tools used?
- Were actions actually executed?
- Was state correct?
- Were permissions respected?
- Did recovery work?
- Was the requested objective actually completed?
- Is the final result useful?

A technically healthy system that fails the user's objective is a GARL failure.

## Autonomy Boundaries

The agent may autonomously:

- inspect code
- run tests
- run builds
- diagnose bugs
- improve tests
- make low-risk implementation fixes
- refactor when required for correctness
- improve documentation

Escalate before:

- deleting major subsystems
- replacing core architecture
- destructive database migrations
- changing security boundaries
- exposing credentials
- weakening permission checks
- introducing paid infrastructure
- major product-direction changes

## Product Principle

GARL should progress toward:

"Give GARL an objective."

not:

"Tell GARL every individual step."

Every major architectural decision should be evaluated against that goal.
