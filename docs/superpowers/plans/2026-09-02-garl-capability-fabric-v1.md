# GARL Capability Fabric V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add availability-aware semantic capabilities that narrow planner tool context, then prove a deterministic research-to-build outcome without changing GARL's concrete execution engine.

**Architecture:** Capability metadata, registry, and resolver sit above the existing `ToolManager`/planner. Concrete `ExecutionPlan` steps remain tool calls; validator, permissions, and durable repository remain authoritative. Research enters through a provider-neutral tool boundary with deterministic fixtures.

**Tech Stack:** Python 3.13, FastAPI, existing dataclasses, SQLite durable repository, pytest, injected fake providers.

**Spec:** `docs/superpowers/specs/2026-09-02-garl-capability-fabric-v1-design.md`

## Global Constraints

- Keep `ToolManager` the only execution surface.
- Do not change durable plan replacement/recovery semantics.
- Use JSON-constrained provider and evidence records; never persist credentials.
- Required CI tests use only fake LLM/research providers.
- Preserve `PermissionService` and `ExecutionPolicy` as tool-level authority.

---

### Task 1: Capability Domain and Registry

**Files:** Create `src/models/capability.py`, `src/services/capability_registry.py`, `tests/services/test_capability_registry.py`; modify `src/core/dependencies.py`.

**Interfaces:** Produce `Capability`, `CapabilityAvailability`, and `CapabilityRegistry(tool_manager)` with `availability(id)`, `available()`, `eligible_tool_names(ids)`, and `planner_description(ids)`.

- [ ] **Step 1: Write failing tests** for missing required tools, optional tools, deterministic ordered descriptions, and unknown IDs.
- [ ] **Step 2: Run** `python -m pytest tests/services/test_capability_registry.py -v`; expect import failure.
- [ ] **Step 3: Implement** frozen JSON-safe dataclasses and registry availability from `ToolManager.get`, with `software_engineering` and `web_research` definitions but no execution behavior.
- [ ] **Step 4: Run focused tests**; expect pass.
- [ ] **Step 5: Inject one cached registry** from the existing manager in dependencies and add a regression that both share tool availability.
- [ ] **Step 6: Commit** `feat: add GARL capability registry`.

### Task 2: Hybrid Capability Resolver

**Files:** Create `src/services/capability_resolver.py`, `tests/services/test_capability_resolver.py`; modify fake LLM fixtures only if an injected selector protocol needs them.

**Interfaces:** Produce `CapabilitySelection(capability_ids, unavailable_reasons, eligible_tool_names)` and `resolve(objective, context) -> CapabilitySelection`.

- [ ] **Step 1: Write failing tests**: research objective selects only web research; prototype objective selects software engineering; unknown/malformed LLM IDs fall back; unavailable IDs are excluded.
- [ ] **Step 2: Run focused tests**; expect missing resolver failure.
- [ ] **Step 3: Implement** normalized deterministic tag scoring plus optional JSON-list selector, registry intersection, stable ordering, and safe empty selection.
- [ ] **Step 4: Run focused tests**; expect pass.
- [ ] **Step 5: Commit** `feat: resolve GARL capabilities safely`.

### Task 3: Planner Context Restriction

**Files:** Modify `src/services/tool_catalog.py`, `src/services/planner_service.py`, `src/services/candidate_plan_generator.py`, `src/services/cognitive_pipeline.py`, `src/services/plan_validator.py`; create or extend `tests/services/test_planner_capabilities.py`.

**Interfaces:** `ToolCatalog.get_tool_definitions(names: set[str] | None)`; planner receives `CapabilitySelection`; validator receives eligible names for one generated plan.

- [ ] **Step 1: Write failing tests** proving a research objective prompt excludes terminal/git/filesystem and a software objective excludes web tools.
- [ ] **Step 2: Run focused tests**; expect all-tool catalog behavior.
- [ ] **Step 3: Implement** subset serialization and capability guidance in prompt construction; retain full manager validation and reject a concrete tool outside the selection.
- [ ] **Step 4: Run focused tests and existing planner tests**; expect pass.
- [ ] **Step 5: Commit** `feat: narrow planner tools by capability`.

### Task 4: Research Provider and Evidence Contracts

**Files:** Create `src/models/research.py`, `src/services/research_provider.py`, `src/services/fake_research_provider.py`, `tests/services/test_research_provider.py`; modify config/dependencies.

**Interfaces:** `ResearchProvider.search(query, limit) -> list[ResearchEvidence]`, `fetch(url) -> ResearchEvidence`; evidence contains URL, title, content, retrieved timestamp, query, provider.

- [ ] **Step 1: Write failing tests** for malformed/blank URLs, deterministic fake results, provider exception normalization, and no credential serialization.
- [ ] **Step 2: Run focused tests**; expect missing contract failure.
- [ ] **Step 3: Implement** constrained dataclasses, fake provider, opt-in real provider config boundary, and no live default.
- [ ] **Step 4: Run focused tests**; expect pass.
- [ ] **Step 5: Commit** `feat: add deterministic research provider boundary`.

### Task 5: Web Search and Fetch Tools

**Files:** Create `src/tools/web_search_tool.py`, `src/tools/web_fetch_tool.py`, `tests/tools/test_web_research_tools.py`; modify `src/tools/registry.py`, `src/services/permission_service.py`, and execution-policy tests.

**Interfaces:** BaseTool names `web_search` and `web_fetch`; JSON schemas require query/url; outputs are provenance-preserving evidence mappings.

- [ ] **Step 1: Write failing tests** for schema validation, fake output provenance, malformed provider output, read-only classification, and zero provider calls after validation failure.
- [ ] **Step 2: Run focused tests**; expect unregistered tool failure.
- [ ] **Step 3: Implement** provider adapters and registry installation; classify only these concrete operations as read-only.
- [ ] **Step 4: Run focused tests plus permission tests**; expect pass.
- [ ] **Step 5: Commit** `feat: add provenance-preserving web research tools`.

### Task 6: Durable Capability Context and Evidence

**Files:** Modify `src/services/agent_service.py`, `src/services/durable_execution_service.py`, durable model/repository only if execution context needs a validated extension; extend `tests/services/test_recovery_service.py` and `tests/api/test_durable_execution_e2e.py`.

**Interfaces:** Store selected capability IDs and evidence references in execution-scoped context before plan persistence; recovery reads them but never reruns resolver for a validated run.

- [ ] **Step 1: Write failing fresh-repository test** asserting capability context/evidence survive and completed research step is skipped.
- [ ] **Step 2: Run focused test**; expect missing context.
- [ ] **Step 3: Implement** narrow JSON context persistence through existing run creation; do not alter plan schema or operation IDs.
- [ ] **Step 4: Run durable recovery/approval/claim tests**; expect pass.
- [ ] **Step 5: Commit** `feat: persist capability context for durable runs`.

### Task 7: Objective Evaluation Gate

**Files:** Create `src/services/objective_evaluator.py`, `tests/services/test_objective_evaluator.py`; modify `src/services/cognitive_pipeline.py` and `src/services/reviewer_service.py` only at the integration seam.

**Interfaces:** `ObjectiveEvaluation(complete, summary, gaps)` and `evaluate(objective, execution_state, artifacts)`. Deterministic evaluator checks benchmark evidence, prototype artifact, and verification observation.

- [ ] **Step 1: Write failing tests** for absent evidence, absent prototype, failed validation, and complete benchmark observations.
- [ ] **Step 2: Run focused tests**; expect missing evaluator failure.
- [ ] **Step 3: Implement** deterministic evaluator and bounded feedback handoff; no reward framework and no durable replan after a persisted plan.
- [ ] **Step 4: Run cognitive/reviewer tests**; expect pass.
- [ ] **Step 5: Commit** `feat: evaluate GARL objective completion`.

### Task 8: Research-to-Decide-to-Build Mission

**Files:** Create `tests/api/test_capability_fabric_mission.py`; extend fake LLM/research fixtures and test-only filesystem/terminal tools.

**Interfaces:** High-level objective only; test graph includes resolver, planner subset, real registry, fake research, concrete tools, evaluator, and fresh durable repository.

- [ ] **Step 1: Write failing mission** asserting research evidence, a reasoned opportunity, prototype file, validation command, useful completion, capability-restricted prompts, and fresh-service no-duplicate continuation.
- [ ] **Step 2: Run mission**; expect capability layer failure.
- [ ] **Step 3: Implement only missing integration seams** identified by the mission.
- [ ] **Step 4: Run mission, full backend compile/test, and deterministic API smoke**; expect pass.
- [ ] **Step 5: Add opt-in live research smoke** skipped unless configuration is explicit, then commit `test: verify GARL research to build mission`.

### Task 9: Final Review and CI Gate

**Files:** Modify only files required by review findings; no frontend redesign or legacy cleanup.

- [ ] **Step 1: Review** `main...HEAD` for second executors, capability risk truth, all-tool prompt leakage, persistence bypasses, credentials, and provider coupling.
- [ ] **Step 2: Run** `python -m compileall src` and `python -m pytest tests -v`; record exact count.
- [ ] **Step 3: Run** deterministic API and mission restart scenarios; inspect final diff with `git diff --check`.
- [ ] **Step 4: Commit** only verified review corrections and request review before publishing.
