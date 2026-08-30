# GARL LLM Runtime Hardening Design

## 1. Problem Statement

GARL's active runtime depends on a single `LLMService` implementation that directly calls LiteLLM with `settings.MODEL_NAME` and `settings.GROQ_API_KEY`. The current local configuration sets `MODEL_NAME=groq/llama-3.3-70b-versatile`; a real `/api/v1/chat` request for `hey` reaches the reasoning engine and then fails because Groq reports that this model does not exist or is not accessible for the account. Automated tests also have no deterministic fake LLM boundary, so end-to-end GARL behavior cannot be validated offline without monkeypatching or live provider availability.

The next milestone must keep GARL's planning, validation, execution, state, permissions, and response contracts intact while making the model/provider boundary explicit, testable, and failure-aware.

## 2. Current Architecture Discovered From Code

The mounted backend runtime starts in `apps/backend/src/main.py`. It creates the FastAPI app, mounts `src.api.v1.chat.router`, and exposes `/`. The chat endpoint is `POST /api/v1/chat`.

The active chat path is:

```text
HTTP POST /api/v1/chat
-> src.api.v1.chat.chat
-> ConversationService.chat
-> AgentService.respond
-> MemoryExtractor.extract
-> MemoryService.retrieve_relevant
-> KnowledgeService.search_context
-> CognitivePipeline.run
-> ReasoningService.analyze
-> CandidatePlanGenerator.generate
-> PlannerService.create_plan
-> PlanParser.parse
-> PlanValidator.validate
-> PlanScorer.score
-> ExecutorService.execute
-> ToolManager / ToolRegistry registered tool
-> PermissionService.evaluate
-> ApprovalService only when a later user approval command resumes pending state
-> ReviewerService.review
-> ResponseComposer.compose
-> CognitiveStateRepository.save
-> ConversationRepository.add_message
-> APIResponse
```

`src.core.dependencies` constructs the active service graph. `get_llm_service()` returns `src.services.llm_service.LLMService`, and that single instance is injected into `ReasoningService`, `PlannerService`, `ExecutorService`, and `MemoryExtractor`.

## 3. Current Live Model Failure Root Cause

The failing model name comes from `.env` through `src.core.config.Settings.MODEL_NAME`. The value observed without exposing secrets is `groq/llama-3.3-70b-versatile`.

The live failure path is:

```text
.env MODEL_NAME and GROQ_API_KEY
-> Settings()
-> LLMService.generate(messages, temperature=0.2, max_tokens=None)
-> litellm.acompletion(model=settings.MODEL_NAME, api_key=settings.GROQ_API_KEY, ...)
-> Groq OpenAI-compatible chat completions endpoint
-> provider error
-> unhandled exception through ReasoningService/CognitivePipeline
-> 500 APIResponse from generic exception handler
```

The normal `hey` runtime did not reach planning or tool execution. Logs showed memory extraction skipped by fast filter, zero memories retrieved, knowledge search attempted, then reasoning began and failed on the LLM call.

A read-only Groq models query using the configured key returned accessible model IDs including `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `groq/compound-mini`, and `groq/compound`; it did not include `llama-3.3-70b-versatile`. A minimal LiteLLM chat call with `groq/openai/gpt-oss-20b` then failed with `invalid_api_key`, so the live provider boundary must distinguish unavailable model failures from credential/request failures.

## 4. Active vs Legacy LLM Implementations

`src.services.llm_service.LLMService` is active. It is imported by `src.core.dependencies`, `ReasoningService`, `PlannerService`, `ExecutorService`, `MemoryExtractor`, `tests/test_llm.py`, and the unmounted legacy planner route.

`src/agents/shared/llm.py` is an empty file. No active code imports it. It is neither a wrapper nor a parallel implementation.

`src/agents/planner/*` is legacy-looking and not imported by the live runtime. It defines a hard-coded planner stack with Pydantic schemas that require task fields the hard-coded planner does not provide. It should not be consolidated or deleted as part of this milestone.

`src/api/routes/planner.py` is also legacy-looking. It imports `LLMService` but calls `generate(system_prompt=..., user_prompt=...)`, which does not match the active `LLMService.generate(messages, ...)` signature. It is not mounted by `src.main`.

## 5. Proposed Provider Boundary

Introduce a narrow LLM boundary under `src/services` rather than replacing GARL with a provider framework.

Conceptual shape:

```text
GARL runtime services
-> LLMService.generate(messages, temperature, max_tokens)
-> configured provider object
   -> LiteLLMProvider for live development/runtime
   -> FakeLLMProvider for deterministic tests/CI
```

`LLMService` remains the active service injected by `core.dependencies`, preserving existing callers. Internally it delegates to a provider selected from configuration. Runtime services should continue to depend on `LLMService`, not directly on LiteLLM or a provider-specific client.

The fake provider must be configured at the service boundary and must not require scattered monkeypatching in tests.

## 6. Configuration Contract

Extend `Settings` with explicit, non-secret LLM configuration:

```python
LLM_PROVIDER: str = "groq"
LLM_MODEL: str
LLM_TIMEOUT_SECONDS: float = 30.0
LLM_MAX_RETRIES: int = 1
LLM_FAKE_MODE: bool = False
```

Compatibility rule: `MODEL_NAME` may remain accepted as a legacy alias during migration, but `LLM_MODEL` is the target field. `GROQ_API_KEY` remains the credential source for the Groq provider. Tests must be able to construct configuration objects directly without reading `.env`.

Configuration validation must fail clearly when the selected provider is unsupported, when required credentials are missing for a real provider, or when the model name is empty.

## 7. Fake-Provider Design

Create a deterministic fake provider with the same async completion contract used by `LLMService`.

The fake provider should return fixture responses based on the intent of the prompt:

- reasoning prompts return the four sections expected by `ReasoningService`.
- planner prompts return GARL execution-plan JSON that exercises no-tool, calculator, denied terminal, approval-required terminal, retry, and resume scenarios.
- executor LLM steps return stable conversational text such as `Hey! GARL is running.`
- memory extraction prompts return `{"memories": []}` unless a test explicitly configures memory fixtures.

The fake provider may accept an in-memory response map for tests that need a specific malformed provider response. The default fake behavior must be deterministic and offline.

## 8. Real-Provider Behaviour

The real provider should use LiteLLM for the current Groq path. `LLMService` should pass provider-selected model, API key, messages, temperature, max token limit, timeout, and retry settings.

A live smoke test may override `LLM_MODEL` to a known accessible model, but model choice remains configuration. The code should not hardcode a specific Groq model outside tests or documentation examples.

## 9. Error Model

Introduce a small GARL-owned LLM exception model:

```python
class LLMError(Exception):
    code: str
    message: str
    provider: str
    model: str | None
    retryable: bool

class LLMConfigurationError(LLMError): ...
class LLMProviderUnavailableError(LLMError): ...
class LLMModelUnavailableError(LLMError): ...
class LLMCredentialsError(LLMError): ...
class LLMMalformedResponseError(LLMError): ...
```

`LLMService.generate()` should normalize provider exceptions into these errors. The API and cognitive pipeline can then report clear failures without exposing secrets.

Credential values must never appear in error messages, logs, test fixtures, or final responses.

## 10. Testing Architecture

Deterministic CI tests should run with fake LLM provider selected through dependency/configuration. These tests must exercise the actual GARL service graph rather than replacing planner/parser/executor with mocks.

Required deterministic layers:

- unit tests for provider selection and configuration validation.
- unit tests for LiteLLM provider error normalization using fake exceptions or injected completion callable.
- service tests for `LLMService` fake provider responses.
- API tests using FastAPI dependency overrides to inject a fake-backed `ConversationService` or fake-backed `AgentService`.
- end-to-end tests for conversation-only, tool execution, DENY, approval-required pause, approval accepted, approval rejected, retry exhaustion, and resume/no-duplicate behavior.

Existing live provider tests remain opt-in. CI must not require network, API keys, provider availability, or external rate limits.

## 11. Live Smoke-Test Policy

Live smoke tests are allowed only when explicitly enabled, for example with `GARL_RUN_LIVE_LLM_TESTS=1`. They require credentials and a configured live model. They should exercise:

```text
uvicorn src.main:app
GET /
POST /api/v1/chat {"conversation_id": "...", "message": "hey"}
```

The expected result is a useful conversational response and no unnecessary tool execution. If the provider fails, the smoke test must report the normalized LLM error and remain outside mandatory CI.

## 12. Router Investigation Findings

`src.main` mounts only:

- `/`
- `/api/v1/chat`

`src.api.router` is not imported by active code. It defines `api_router = APIRouter()` and includes `planner.router`, then calls `router.include_router(...)` even though `router` is not defined. Importing this module would fail at runtime.

`src.api.v1.cognitive` defines `/cognitive/{conversation_id}`, but it is not mounted by `src.main`. `src/api/routes/health.py`, `executor.py`, `memory.py`, and `reviewer.py` are empty. `src/api/routes/planner.py` is unmounted and incompatible with the active LLM service signature.

The current frontend is the default Next page and does not call GARL backend routes. No existing tests depend on `src.api.router`.

Routing should not be changed in this milestone unless the implementation of deterministic API tests proves a required public path is broken.

## 13. Security and Secrets Constraints

The implementation must not print `.env` contents. API keys may be checked for presence, but values must be redacted. Logs and exceptions must not include provider authorization headers, raw credential values, or full environment dumps.

Fake-provider tests must not require real credentials. Live smoke tests must be opt-in and skipped clearly when required credentials or live model configuration are absent.

## 14. Compatibility and Migration Strategy

Keep `LLMService.generate(messages, temperature=0.2, max_tokens=None) -> str` as the public caller contract for this milestone.

Migrate configuration by accepting both `LLM_MODEL` and the legacy `MODEL_NAME`, with `LLM_MODEL` preferred when both are present. Keep `GROQ_API_KEY` for the Groq provider. Existing callers in reasoning, planning, executor LLM steps, and memory extraction should not need signature changes.

Do not update unmounted legacy agents or routes beyond documenting them unless they block active runtime tests.

## 15. Explicit Non-Goals

- Do not replace GARL with LangGraph, an agent framework, or a broad provider abstraction.
- Do not mount or delete legacy routers as part of LLM hardening.
- Do not weaken `PlanParser` or `PlanValidator` to accept arbitrary malformed output.
- Do not make live LLM tests mandatory in CI.
- Do not commit credentials or example real API keys.
- Do not remove `src/agents/*` during this milestone.

## 16. Acceptance Criteria

- Baseline startup and executor permission fixes remain committed and green.
- `LLMService` has a clear provider boundary with real and fake providers.
- Fake LLM can run deterministic GARL API tests offline.
- Missing credentials, unavailable model, provider outage, and malformed response are reported through GARL-owned error types.
- Mandatory backend tests pass without network access or live API keys.
- Live smoke test is opt-in and reports either a useful `hey` response or a normalized provider/configuration error.
- Router split is documented with evidence and left unchanged unless a required active path is broken.

## 17. Risks

- LiteLLM exception classes may vary by provider and version, so error normalization must be tested with representative failures rather than only class names.
- Current `CognitivePipeline` lets LLM exceptions escape during reasoning, so the first implementation pass must decide whether to catch normalized LLM errors in the API layer, the pipeline, or both.
- The in-memory state repositories make resume behavior testable in one process but do not provide durable recovery across process restarts.
- Legacy route and agent files can confuse future contributors until routing ownership is clarified.
- A fake provider can drift from real provider behavior if tests assert only happy paths; malformed and failure fixtures are required.
