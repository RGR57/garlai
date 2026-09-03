# GARL Web Operator V1 Design

## 1. GARL North Star and Problem

GARL accepts an arbitrary digital outcome, determines required work, uses only selected concrete tools, observes external reality, asks for approval at consequential boundaries, and resumes safely after interruption. Browser operation extends that path to browser-based environments; it does not create a website-specific agent, a second planner, or a browser-only runtime.

Today GARL has no active browser implementation. `src/tools/browser/` is empty, `requirements.txt` has no Playwright, Selenium, or browser dependency, and `core/dependencies.py` registers calculator, terminal, filesystem, git, and web search only. The active durable path is `AgentService -> CognitivePipeline -> PlannerService/PlanValidator -> ExecutorService -> ToolManager -> PermissionService/ApprovalService -> DurableExecutionService/SQLite -> RecoveryService`. Browser work must remain on that path.

## 2. Existing Runtime Facts

`CapabilityRegistry` derives semantic capability availability from the active `ToolManager`; `CapabilityResolver` stores a selected-capability snapshot in durable execution context; `ToolCatalog` and `PlanValidator` restrict the planner to those selected concrete tools. `ExecutorService` freezes resolved arguments, checks permission, atomically claims consequential operations, invokes a tool, and records a proven outcome or `UNCERTAIN`. `ApprovalService` approves one exact execution-bound payload hash. `RecoveryService` reloads the run, rebuilds `ExecutionState`, skips completed work, and converts orphaned consequential intents to `RECOVERY_REQUIRED`.

`ExecutionRun.execution_context`, variables, durable steps, result metadata, artifacts, operation journal, and approval journal are JSON-only durable facts. They must not contain provider handles, cookies, DOM nodes, browser processes, or credential values. `ObjectiveEvaluator` determines whether observable objective requirements, not merely plan steps, were met.

## 3. Architecture Options

**A. Playwright inside each browser tool** has the smallest initial file count, but duplicates page lifecycle, recovery, target reconciliation, redirect policy, and secret handling across tools. It makes deterministic tests and future provider replacement weaker.

**B. BrowserSessionService plus BrowserProvider plus normal GARL tools** gives one owner for session isolation, structured observation, semantic resolution, reconciliation, and provider lifecycle. Tools remain ordinary `BaseTool` primitives, so the existing validator, policy, approvals, durable journal, and executor retain authority. It supports a deterministic fake provider and a real Playwright adapter without coupling GARL core to Playwright objects.

**C. A hosted browser service or independent browser agent runtime** could improve later deployment isolation, but adds a second scheduler, planner/executor semantics, and remote credential/session protocol before V1 proves the local contract.

V1 selects **Option B**. A remote provider can later implement the same `BrowserProvider` interface. No `BrowserAgent`, `BrowserExecutor`, autonomous browser loop, or direct Playwright calls in GARL tools are permitted.

## 4. Web Operation Capability and Tool Scope

Add `web_operation` to `CapabilityRegistry`. It is available only when all required browser tools and the configured browser session provider are registered. It has tags including `browser`, `website`, `web`, `signup`, `form`, `portal`, `plan`, `dashboard`, and `operate`; it produces `browser_observation`, `prepared_action`, and `browser_confirmation` facts. Capability metadata grants neither permission nor approval.

V1 registers exactly five concrete tools:

| Tool | Purpose | Default safety |
| --- | --- | --- |
| `browser_navigate` | Safely move the execution session to an allowed URL. | Read-only, low risk |
| `browser_observe` | Return bounded structured page state. | Read-only, low risk |
| `browser_select` | Make a preparatory semantic selection. | Consequential, medium risk, allowed |
| `browser_fill` | Fill a permitted non-sensitive field. | Consequential, medium risk, allowed |
| `browser_submit` | Invoke a semantic final commit target. | Consequential, high risk, approval required |

There is no generic `browser_action`, arbitrary JavaScript execution, raw selector tool, upload/download, back/tabs, screenshot-first control, or generic click tool in V1. Navigation handles page movement; selection and fill cover benchmark preparation; submit is the sole final commitment primitive. This small set keeps permission and approval meaning visible.

## 5. Browser Provider, Session Service, and Invocation Context

`BrowserProvider` is a technology-neutral async protocol. Its methods create and close an opaque session, navigate with a `NavigationPolicy`, observe structured accessibility/DOM facts, and perform semantic selection, fill, and submit operations. Its values are GARL domain records, never Playwright classes. `PlaywrightBrowserProvider` is the production adapter and owns Chromium/context/page objects internally. `FakeBrowserProvider` supplies deterministic unit tests. A local Playwright-backed fixture exercises the same provider contract in integration tests without Internet access.

`BrowserSessionService` owns exactly one in-memory provider session per durable `execution_id`. It maps that execution to a generated logical `browser_session_id`, creates or closes ephemeral provider sessions, applies navigation policy before every document request and redirect, obtains bounded observations, resolves semantic targets, redacts sensitive data, persists browser facts through the durable repository, and reconciles a fresh provider session from durable facts. It is a service, not an agent: it never chooses the next GARL action or calls the planner.

Add a generic `ToolInvocationContext(execution_id, step_id, operation_id, approved_payload_hash)` and `ToolManager.execute(tool_name, arguments, invocation)`. The manager's default path calls existing tools unchanged. Browser tools require a non-empty durable execution identity and receive it only through this executor-owned context, never through planner-controlled arguments. `BaseTool.execute_with_context(arguments, invocation)` defaults to `execute(**arguments)`; browser tools override it. `ExecutorService` and durable `ApprovalService` call the manager rather than calling tools directly.

## 6. Observation and Element Identity

`BrowserObservation` is constrained JSON with `observation_id`, `browser_session_id`, normalized URL, title, bounded visible text, a bounded list of `BrowserElement`, timestamp, navigation sequence, and a page fingerprint. Each `BrowserElement` contains an observation-local `element_ref`, semantic role, accessible name, optional label, limited text context, form relationship, and semantic fingerprint. Limits are fixed in code: at most 100 elements, 12,000 visible-text characters, 500 characters per element context, and no raw HTML or screenshot by default.

An `element_ref` is valid only for its `observation_id`. A durable `BrowserTarget` carries that local reference plus the session ID, observed URL/origin, role, accessible name or label, form/context facts, and semantic fingerprint. On a fresh page the service resolves the target by role and accessible name, then label/form/context and fingerprint. It must find exactly one matching live element. Zero or multiple matches, a changed origin/path, or a changed commit-context fingerprint is a deterministic reconciliation failure; raw CSS selectors are neither planner input nor the sole identity mechanism.

To let GARL reason over a real observation without a second planner, add a constrained `PlanStep.result_contract` for tool-free LLM steps. `browser_target` permits the LLM to return only a JSON target selected from a supplied observation's elements; the executor validates it against that observation and stores a native `BrowserTarget`. `browser_verification` permits only a JSON assertion with evidence references from a supplied final observation. Extend `VariableResolver` so an exact reference such as `{{step3}}` preserves its validated JSON value instead of stringifying it; embedded references remain scalar-only. This allows an already validated plan to observe, choose from current facts, prepare, submit, and verify without hidden site-specific logic.

## 7. Planner and Trust Boundary

`web_operation` selection exposes only the five browser tools and the constrained result-contract guidance. A web-operation-only objective cannot see terminal, filesystem, research, or git. A multi-capability objective receives the union already authorized by `CapabilityResolver`; `PlanValidator` rejects any registered tool outside that union.

Web page content is untrusted data. `browser_observe` results are rendered into LLM context under a fixed `UNTRUSTED EXTERNAL PAGE DATA` boundary. They may support factual selection and verification but cannot add tools, change the objective, grant permissions, request approval, reveal secrets, choose a session, or authorize filesystem, terminal, git, or research actions. Browser observation is bounded before rendering. Tests include page text that instructs GARL to reveal secrets, execute terminal commands, and submit immediately; no such content can expand capability selection, tool eligibility, permission, or approval.

## 8. Risk, Approval, and Commit Preflight

`PermissionService` remains authoritative. Navigate and observe return `READ_ONLY_POLICY` and are low risk. Select and fill are `CONSERVATIVE_POLICY` but are allowed at medium risk: a page can autosave or mutate remote state, so a crash after dispatch is never retried blindly. Submit is `CONSERVATIVE_POLICY`, high risk, and always requires approval. Unknown browser tool/action semantics are denied.

Preparatory selection/fill may proceed without approval only after normal validation and atomic operation claim. `browser_submit` cannot invoke before a durable `ApprovalRequest` freezes the execution ID, operation ID, tool, action, target/session facts, URL/origin, semantic target, non-sensitive relevant fields, and canonical payload hash.

Before a user-approved submit is claimed or clicked, `ToolManager.preflight` calls `BrowserSessionService.preflight_commit`. It reobserves the live page and resolves the frozen `BrowserTarget`. The origin/path, semantic target, selected choice/form facts, and commit-context fingerprint must match the frozen payload. A mismatch guarantees no click occurred, appends an `INVALIDATED` approval journal fact, records a known non-invocation, and transitions the execution to `RECOVERY_REQUIRED`; the old approval never authorizes a newly rendered button. Only a ready preflight may claim and invoke the operation.

Add `ToolInvocationOutcome` with `NOT_INVOKED`, `CONFIRMED`, and `UNKNOWN`. Existing consequential-tool failures remain conservatively `UNKNOWN`. Browser tools report `NOT_INVOKED` only when the provider proves no dispatch occurred, such as preflight mismatch. Submit returns `CONFIRMED` only after its click path and required immediate provider confirmation complete; lack of confirmation or an acknowledgement loss is `UNKNOWN`. The executor records a known failure for `NOT_INVOKED` and `UNCERTAIN`/`RECOVERY_REQUIRED` for `UNKNOWN`.

## 9. Durable Facts, Recovery, and Reconciliation

The durable execution context gains a bounded `browser` object: logical session ID, last verified URL, latest sanitized observation summary/fingerprint, completed action facts, selected non-sensitive values or value hashes, expected postconditions, and timestamps. Step results retain useful observation, target, receipt, and confirmation references. Raw DOM, screenshots, cookies, auth headers, provider handles, passwords, CSRF tokens, payment data, and resolved secret values are forbidden from durable context, logs, planner prompts, artifacts, and test snapshots.

`RecoveryService` gains a narrow `ExecutionReconciler` protocol. When browser facts exist, the injected `BrowserSessionService` creates a new provider session, safely navigates to the last verified allowed URL, observes reality, compares the persisted fingerprint and semantic facts, and atomically records the reconciliation observation. It does not replay prior select, fill, or submit actions. A matching prepared state permits the next pending normal plan step. A material mismatch is `RECOVERY_REQUIRED` with an actionable reason.

For an orphaned browser submit intent, recovery asks the browser reconciler to inspect the external page before generic orphan handling. A visible success confirmation with matching target/operation evidence records the completed outcome. Any result that cannot prove success remains `UNCERTAIN` and `RECOVERY_REQUIRED`; GARL never clicks submit again automatically. The generic operation journal remains the source of operation identity and claim truth.

## 10. Navigation, Authentication, and Sensitive Data

Production navigation permits only public `https://` origins. It rejects `file:`, `data:`, `javascript:`, `chrome:`, extension schemes, embedded URL credentials, loopback, link-local, private, and cloud-metadata addresses. The navigation guard is enforced before initial navigation and every redirect/request that can replace the document, after host normalization and address classification. A test-only injected policy permits the single dynamically allocated local fixture origin; no setting enables localhost in production.

V1 supports public pages and a provider abstraction for a future pre-authenticated session. It does not store credentials, cookies, password-manager values, MFA state, CAPTCHA results, or payment data. `browser_fill` accepts an explicit non-sensitive literal only for a provider-declared non-sensitive field, or an opaque `secret_ref` resolved at runtime by a future secret boundary. It rejects password-like fields and never returns typed values in observations. Unexpected login, CAPTCHA, download/upload, or sensitive field requirements stop the run with a structured unsupported/recovery reason.

## 11. Objective Evaluation and Benchmarks

Extend the existing deterministic `ObjectiveEvaluator`; do not create a browser-specific evaluator. It reads browser receipts and verified observations and requires, when the objective asks for them: a selected qualifying plan, prepared non-sensitive form facts, a durable approval before submit, exactly one confirmed operation outcome, and a final observation carrying the validated success assertion. Step completion alone is insufficient.

The deterministic local test site is test infrastructure, not a GARL feature. It is a small local SaaS marketplace with fixture-provided Starter, Pro, and Business plans, prices, user limits, and SSO flags; pricing values vary between tests. The benchmark objective is: "On this SaaS marketplace, find the cheapest plan that supports SSO and at least 10 users, prepare the signup using the supplied TEST details, and ask me before making the final commitment." The plan observes current data, a constrained LLM target decision selects the cheapest qualifying observed plan, fills test data, pauses before submit, and verifies the real local success state after approval.

Required mission variants prove: before approval there is no submit; rejection produces no commit; approval invokes the exact frozen submit at most once; a reconstructed GARL/browser service reconciles prepared state without replaying completed work; and a lost submit acknowledgement is reconciled to success only when visible evidence proves it, otherwise becomes `RECOVERY_REQUIRED`. CI uses fake-provider unit tests plus local Playwright integration tests only; no public website, Brave/Groq key, external browser service, or credential is required.

## 12. Non-Goals, Future Extension, and Acceptance

V1 excludes real payments, purchases, financial transactions, CAPTCHA or anti-bot bypass, credential vaults, MFA, email/calendar/CRM integrations, desktop or OS control, arbitrary uploads/downloads, production deployment infrastructure, distributed browser workers, scheduling, visual-first control, and frontend redesign. A future `computer_use` capability may consume screenshots and coordinate fallbacks behind the same capability and durable-operation boundaries, but V1 is DOM/accessibility first.

Acceptance requires all of the following:

1. Browser actions execute solely through the existing planner, validator, executor, manager, permissions, approvals, and durable journals.
2. `web_operation` availability and planner context are capability-scoped from actual registrations.
3. Observation is bounded, structured, and untrusted; page text cannot cross-authorize other capabilities.
4. Semantic targets survive rerender/restart only by safe reconciliation, never selector-only replay.
5. Preparatory mutations are journaled conservatively; submit requires exact approval plus preflight and is never duplicated after uncertainty.
6. Browser context is isolated by execution ID and persists logical facts only.
7. Production navigation rejects unsafe schemes and private/local destinations; local fixture access is test-only.
8. The local benchmark proves dynamic cheapest-plan reasoning, approval/rejection, restart recovery, uncertain-submit handling, and objective completion.
