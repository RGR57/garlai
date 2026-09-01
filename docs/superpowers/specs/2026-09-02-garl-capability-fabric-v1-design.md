# GARL Capability Fabric V1 Design

## 1. North Star

GARL accepts an arbitrary digital outcome, determines the work required, chooses available capabilities and concrete tools, observes results, asks for approval where necessary, and continues safely until the outcome is fulfilled or a durable recovery condition requires human action. Building software is one capability, not the product identity.

## 2. Problem

The current planner receives a JSON description of every registered tool on every planning call. This works for four tools, but does not scale in tokens, relevance, or safety surface. It also does not give GARL a semantic answer to which kinds of work are currently possible.

## 3. Existing Architecture

`core/dependencies.py` builds one `ToolManager` and populates it through `tools/registry.py`. The active registry installs calculator, terminal, filesystem, and git. `ToolCatalog` serializes every manager tool; `PlannerService.create_plan` embeds that complete catalog in its prompt. `PlanValidator` validates concrete tool names and arguments against the same manager. `ExecutorService` resolves arguments, calls `PermissionService`, claims durable operations, invokes concrete tools, and records outcomes. `AgentService` persists a validated `ExecutionPlan` before durable continuation. `RecoveryService` resumes that persisted plan without regeneration.

`services/tool_registry.py` is a duplicate read-only wrapper around `ToolManager`, while `services/tool_router.py` is an unused calculator-keyword prototype. `tools/registry.py` is the active registration point. Neither redundant abstraction is deleted in V1.

## 4. Scaling Limitation

Sending all tool descriptions means unrelated tools appear in the planner context, increases tokens linearly, and encourages unsuitable selection. The remedy is planner-context filtering, not another executor.

## 5. Definitions

**Tool**: a concrete executable primitive with a schema and `execute`; `ToolManager` is authoritative.

**Capability**: semantic metadata stating that a class of work is possible only when its prerequisites are available. It is not executable and has no authority over risk.

**Skill/workflow**: a future reusable multi-capability method. V1 defines no skill execution, marketplace, or workflow engine.

## 6. Options

Option A, tool tags only, is small but lacks availability, prerequisite explanations, and a durable semantic boundary. Option C, executable composite capabilities, duplicates the executor and risks bypassing safety. Option B, capability definitions plus registry plus resolver over `ToolManager`, preserves proven contracts while giving semantic planning context. V1 selects **Option B**.

## 7. Capability Contract

Add immutable domain records:

```python
@dataclass(frozen=True)
class Capability:
    capability_id: str
    name: str
    description: str
    tags: tuple[str, ...]
    required_tools: tuple[str, ...]
    optional_tools: tuple[str, ...]
    input_classes: tuple[str, ...]
    output_classes: tuple[str, ...]
    planner_guidance: str

@dataclass(frozen=True)
class CapabilityAvailability:
    capability: Capability
    available: bool
    missing_required_tools: tuple[str, ...]
```

The contract contains no permission decision, risk level, approval rule, or execution implementation. Those remain tool-level truth in `PermissionService` and `ExecutionPolicy`.

## 8. Registry and Availability

`CapabilityRegistry(tool_manager)` owns the canonical definitions and derives availability on demand from `ToolManager.get`. It exposes `list`, `get`, `availability`, `available`, `eligible_tool_names`, and a deterministic planner description. Missing required tools make a capability unavailable with an explicit reason; optional tools improve guidance but never availability. The dependency provider constructs one registry from the existing manager.

## 9. Resolver

Use a hybrid resolver. Deterministic normalized tag/objective matching supplies an offline baseline and selects no unavailable ID. An optional schema-constrained LLM selector may nominate IDs from the registry-provided candidate list; its output is parsed as a JSON list, deduplicated, and intersected with available IDs. Unknown, malformed, or unavailable IDs are rejected and fall back to deterministic results. If neither path yields a capability, planning receives only the conversational LLM path and no concrete tools. Fake LLM selection fixtures are deterministic.

## 10. Planner Integration

Before generating a new plan, `CognitivePipeline` resolves capabilities from the original objective and current planning context. It passes `CapabilitySelection` to `PlannerService.create_plan`. The planner receives the selection's planner guidance plus `ToolCatalog` restricted to the registry-derived eligible tool names. `PlanValidator` still validates the complete manager so a proposed unselected tool is rejected by a new eligible-tool validation input as well as ordinary name/schema checks. `ExecutionPlan` remains concrete-tool based.

Validated durable plans persist exactly as today. Capability selection is planning-time context only and is persisted in execution context for audit. A recovery of a validated run never invokes the resolver or planner.

## 11. Software Engineering Capability

`software_engineering` requires filesystem and terminal, with git optional. Tags include `software`, `code`, `prototype`, `test`, `build`, and `repository`. Guidance covers inspect/edit files, run commands and verification, then observe results. Filesystem writes, terminal commands, and git mutations retain their existing permission classification.

## 12. Web Research Capability

`web_research` requires `web_search` and optionally `web_fetch`. Tags include `research`, `market`, `competitor`, `opportunity`, `source`, and `evidence`. It produces execution-scoped research evidence, not long-term memory.

Introduce a provider-neutral `ResearchProvider` protocol with `search(query, limit)` and `fetch(url)` returning constrained dataclasses. `WebSearchTool` and `WebFetchTool` adapt that protocol to `BaseTool` and return structured JSON evidence. A real provider adapter is selected by configuration, while a fake provider has frozen source URL/title/content/timestamp fixtures.

Brave Search is the recommended first real search adapter because its official API exposes a web-search endpoint over a public index. Tavily is a viable alternate adapter because it returns structured result content and has a separate extraction endpoint. GARL core depends only on `ResearchProvider`, not either SDK or response shape. Both require API credentials and may rate-limit, so live smoke tests are opt-in. [Brave API](https://api-dashboard.search.brave.com/api-reference/web/search/get), [Tavily search API](https://docs.tavily.com/documentation/api-reference/endpoint/search).

## 13. Evidence and Provenance

`ResearchEvidence` contains source URL, title, extracted content or bounded summary, retrieval timestamp, query, and minimal provider identifier. It validates JSON-only data and rejects blank URLs. Tool output contains evidence records, and durable step result/artifact metadata stores the reference needed by later steps. No vector store, memory repository, or global research corpus is introduced.

## 14. Deterministic and Live Testing

`FakeResearchProvider` is the required CI default and returns stable realistic sources. Tests never call the internet or need provider credentials. `LiveResearchProvider` smoke tests are explicitly skipped unless the selected provider credential and opt-in setting are present; they verify only schema/provenance, not ranking.

## 15. Outcome Evaluation

Current `ReviewerService` only checks the last step result, so V1 adds a small `ObjectiveEvaluator` boundary that receives the original objective, observed step results, and produced artifacts/evidence. It returns `complete`, `summary`, and explicit gaps. The deterministic evaluator verifies benchmark invariants; an optional LLM evaluator remains advisory and cannot mark an absent artifact/check as complete. `CognitivePipeline` uses an incomplete evaluation as reviewer feedback for a bounded replan, never as a reason to replace a persisted durable plan.

## 16. Failure and Recovery

Unknown/unavailable capabilities are excluded with reasons. Empty selection uses the normal no-tool path. Provider failure, malformed research data, no sources, tool failure, failed prototype verification, and evaluator gaps become structured observations/feedback. Recoverable failures may produce a new plan only before durable plan persistence; consequential ambiguity remains `UNCERTAIN`/`RECOVERY_REQUIRED`, and approvals remain immutable. No capability can override permission policy.

## 17. Benchmark

The deterministic objective is: research frozen market evidence, decide an underserved digital opportunity, create a local prototype, and verify it. The fake provider yields at least two cited sources describing a common problem and missing workflow. Resolver selects web research then software engineering; planner receives only those capability tools. The generated concrete plan searches/fetches, writes prototype files, runs a deterministic validation command, and evaluates evidence plus artifact/check output. The mission asserts provenance, real tool calls, artifact existence, verification success, a useful result, and no duplicate work after fresh-service recovery.

## 18. Compatibility, Non-Goals, and Risks

Existing `ToolManager`, `ToolRegistry`, parser, validator, permissions, approvals, executor, and durable state are reused. No legacy cleanup, second executor, browser automation, marketplace, background scheduler, deployment, vector DB, general memory persistence, payment, or frontend redesign is in scope.

Risk remains in resolver relevance, research-provider availability and terms, content trust, and benchmark overfitting. Mitigations are conservative registry validation, provider isolation, provenance retention, fake fixtures, bounded content, tool-level enforcement, and mission tests with unrelated tools present.

## 19. Acceptance Criteria

1. Available capabilities and unavailable reasons derive from actual registered tools.
2. Planner context contains only resolver-eligible tool definitions.
3. Unknown capability suggestions cannot select tools or bypass validation.
4. Capability metadata never changes tool permission/risk behavior.
5. Validated durable plans resume unchanged after restart.
6. Fake research is deterministic with provenance; live research is opt-in.
7. The Research-to-Decide-to-Build mission collects evidence, creates and verifies a prototype, evaluates fulfillment, and survives fresh-service reconstruction without duplicate completed/consequential work.
