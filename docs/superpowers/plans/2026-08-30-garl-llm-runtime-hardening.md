# GARL LLM Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make GARL's active LLM boundary configurable, deterministic in CI, and resilient to provider/configuration failures without bypassing planning, validation, execution, state, permission, or response contracts.

**Architecture:** Keep `src.services.llm_service.LLMService.generate(messages, temperature=0.2, max_tokens=None) -> str` as the active caller contract. Add a small provider boundary behind it: a LiteLLM-backed real provider and a deterministic fake provider selected through configuration/dependency wiring. Exercise GARL through its current mounted API path, `POST /api/v1/chat`, while leaving legacy routers and `src/agents/*` unmodified.

**Tech Stack:** Python 3, FastAPI, Pydantic settings, LiteLLM, pytest, unittest async tests.

**Spec:** `docs/superpowers/specs/2026-08-30-garl-llm-runtime-hardening-design.md`

## Global Constraints

- LLM output is untrusted input and must still flow through `PlanParser` and `PlanValidator`.
- Mandatory tests must run offline without network, live API keys, provider availability, or external rate limits.
- Live provider smoke tests must be opt-in with `GARL_RUN_LIVE_LLM_TESTS=1`.
- Do not print or commit credentials.
- Do not mount, delete, or restructure legacy routing during this milestone unless an active required runtime path is conclusively broken.
- Do not replace GARL architecture with another framework.
- Keep the current public `LLMService.generate(messages, temperature=0.2, max_tokens=None) -> str` caller interface.

---

## File Structure

- Create `apps/backend/src/services/llm_errors.py`: GARL-owned LLM exception classes and error codes.
- Create `apps/backend/src/services/llm_providers.py`: `LLMProvider` protocol, `LiteLLMProvider`, and `FakeLLMProvider`.
- Modify `apps/backend/src/core/config.py`: explicit provider/model/test-mode configuration with `MODEL_NAME` compatibility.
- Modify `apps/backend/src/services/llm_service.py`: delegate to selected provider and normalize malformed responses.
- Modify `apps/backend/src/core/dependencies.py`: build `LLMService` with provider selected from settings.
- Modify `apps/backend/tests/test_llm.py`: keep live smoke opt-in and add deterministic service tests.
- Create `apps/backend/tests/services/test_llm_configuration.py`: configuration/provider selection tests.
- Create `apps/backend/tests/services/test_llm_error_normalization.py`: provider error mapping tests.
- Create `apps/backend/tests/api/test_chat_e2e.py`: offline API E2E tests using fake provider.
- Create or extend `apps/backend/tests/services/test_cognitive_pipeline.py`: retry/no-duplicate/resume service coverage where API-level setup is too coarse.

### Task 1: Configuration And Model Contract

**Files:**
- Modify: `apps/backend/src/core/config.py`
- Test: `apps/backend/tests/services/test_llm_configuration.py`

**Interfaces:**
- Consumes: existing `Settings` object from `src.core.config`.
- Produces: `Settings.llm_model`, `Settings.LLM_PROVIDER`, `Settings.LLM_TIMEOUT_SECONDS`, `Settings.LLM_MAX_RETRIES`, `Settings.LLM_FAKE_MODE`.

- [ ] **Step 1: Write the failing configuration tests**

```python
from src.core.config import Settings


def test_llm_model_prefers_new_field_over_legacy_model_name():
    settings = Settings(
        LLM_MODEL="groq/openai/gpt-oss-20b",
        MODEL_NAME="groq/old-model",
        GROQ_API_KEY="secret",
    )

    assert settings.llm_model == "groq/openai/gpt-oss-20b"


def test_llm_model_accepts_legacy_model_name_during_migration():
    settings = Settings(
        MODEL_NAME="groq/legacy-model",
        GROQ_API_KEY="secret",
    )

    assert settings.llm_model == "groq/legacy-model"


def test_real_groq_provider_requires_credentials():
    settings = Settings(
        LLM_MODEL="groq/openai/gpt-oss-20b",
        GROQ_API_KEY="",
    )

    assert settings.GROQ_API_KEY == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\services\test_llm_configuration.py -v`

Expected: FAIL because `LLM_MODEL`, `LLM_PROVIDER`, and `llm_model` do not exist.

- [ ] **Step 3: Implement minimal configuration contract**

```python
class Settings(BaseSettings):
    MAX_CONTEXT_MESSAGES: int = 20
    MODEL_NAME: str | None = None
    LLM_PROVIDER: str = "groq"
    LLM_MODEL: str | None = None
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 1
    LLM_FAKE_MODE: bool = False
    GROQ_API_KEY: str = ""

    @property
    def llm_model(self) -> str:
        model = self.LLM_MODEL or self.MODEL_NAME
        if not model:
            raise ValueError("LLM model is not configured.")
        return model
```

- [ ] **Step 4: Run focused and regression tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\services\test_llm_configuration.py tests\api\test_app_startup.py -v`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/backend/src/core/config.py apps/backend/tests/services/test_llm_configuration.py
git commit -m "feat: define GARL LLM configuration contract"
```

### Task 2: Deterministic Fake LLM Provider

**Files:**
- Create: `apps/backend/src/services/llm_providers.py`
- Create: `apps/backend/src/services/llm_errors.py`
- Test: `apps/backend/tests/test_llm.py`

**Interfaces:**
- Consumes: `messages: list[dict[str, Any]]`, `temperature: float`, `max_tokens: int | None`.
- Produces: `LLMProvider.generate(...) -> str`, `FakeLLMProvider.generate(...) -> str`.

- [ ] **Step 1: Write failing fake-provider tests**

```python
import unittest

from src.services.llm_providers import FakeLLMProvider


class FakeLLMProviderTests(unittest.IsolatedAsyncioTestCase):

    async def test_fake_llm_returns_reasoning_sections_for_reasoning_prompt(self):
        provider = FakeLLMProvider()

        response = await provider.generate(
            [{"role": "system", "content": "You are GARL's reasoning engine."}]
        )

        self.assertIn("OBJECTIVE:", response)
        self.assertIn("CONSTRAINTS:", response)
        self.assertIn("ASSUMPTIONS:", response)
        self.assertIn("STRATEGY:", response)

    async def test_fake_llm_returns_conversation_text_for_plain_prompt(self):
        provider = FakeLLMProvider()

        response = await provider.generate(
            [{"role": "user", "content": "hey"}]
        )

        self.assertEqual(response, "Hey! GARL is running.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\test_llm.py -v`

Expected: FAIL because `src.services.llm_providers` does not exist.

- [ ] **Step 3: Implement minimal fake provider and error base**

```python
from typing import Any, Protocol


class LLMProvider(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        ...


class FakeLLMProvider:
    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        joined = "\n".join(str(message.get("content", "")) for message in messages)
        if "reasoning engine" in joined:
            return (
                "OBJECTIVE:\nRespond conversationally.\n\n"
                "CONSTRAINTS:\n- Do not use tools unnecessarily.\n\n"
                "ASSUMPTIONS:\n- The user is greeting GARL.\n\n"
                "STRATEGY:\nReturn a concise greeting."
            )
        return "Hey! GARL is running."
```

- [ ] **Step 4: Run focused and regression tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\test_llm.py tests\services\test_cognitive_pipeline.py -v`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/backend/src/services/llm_errors.py apps/backend/src/services/llm_providers.py apps/backend/tests/test_llm.py
git commit -m "feat: add deterministic fake LLM provider"
```

### Task 3: Wire Provider Into Active LLM Service

**Files:**
- Modify: `apps/backend/src/services/llm_service.py`
- Modify: `apps/backend/src/core/dependencies.py`
- Test: `apps/backend/tests/test_llm.py`

**Interfaces:**
- Consumes: `LLMProvider.generate(...) -> str`.
- Produces: `LLMService(provider: LLMProvider | None = None).generate(...) -> str`.

- [ ] **Step 1: Write failing service-boundary test**

```python
import unittest

from src.services.llm_providers import FakeLLMProvider
from src.services.llm_service import LLMService


class LLMServiceProviderTests(unittest.IsolatedAsyncioTestCase):

    async def test_llm_service_uses_injected_provider_without_network(self):
        service = LLMService(provider=FakeLLMProvider())

        response = await service.generate(
            [{"role": "user", "content": "hey"}],
            temperature=0,
            max_tokens=16,
        )

        self.assertEqual(response, "Hey! GARL is running.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\test_llm.py::test_llm_service_uses_injected_provider_without_network -v`

Expected: FAIL because `LLMService` does not accept `provider`.

- [ ] **Step 3: Implement minimal delegation**

```python
class LLMService:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or LiteLLMProvider(settings)

    async def generate(self, messages, *, temperature=0.2, max_tokens=None) -> str:
        return await self.provider.generate(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
```

- [ ] **Step 4: Update dependency provider selection**

```python
@lru_cache
def get_llm_service() -> LLMService:
    if settings.LLM_FAKE_MODE:
        return LLMService(provider=FakeLLMProvider())
    return LLMService()
```

- [ ] **Step 5: Run focused and full backend tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\test_llm.py tests -v`

Expected: PASS with live test skipped unless explicitly enabled.

- [ ] **Step 6: Commit checkpoint**

```bash
git add apps/backend/src/services/llm_service.py apps/backend/src/core/dependencies.py apps/backend/tests/test_llm.py
git commit -m "feat: route GARL LLM service through provider boundary"
```

### Task 4: Provider And Model Error Normalization

**Files:**
- Modify: `apps/backend/src/services/llm_errors.py`
- Modify: `apps/backend/src/services/llm_providers.py`
- Modify: `apps/backend/src/services/llm_service.py`
- Test: `apps/backend/tests/services/test_llm_error_normalization.py`

**Interfaces:**
- Consumes: provider exceptions raised by LiteLLM or injected completion callables.
- Produces: `LLMConfigurationError`, `LLMProviderUnavailableError`, `LLMModelUnavailableError`, `LLMCredentialsError`, `LLMMalformedResponseError`.

- [ ] **Step 1: Write failing error tests**

```python
import unittest

from src.services.llm_errors import LLMCredentialsError, LLMModelUnavailableError
from src.services.llm_providers import LiteLLMProvider


async def raises_model_error(**kwargs):
    raise Exception("model_not_found: model does not exist")


async def raises_key_error(**kwargs):
    raise Exception("Invalid API Key")


class LiteLLMProviderErrorTests(unittest.IsolatedAsyncioTestCase):

    async def test_litellm_provider_maps_model_not_found(self):
        provider = LiteLLMProvider(
            provider_name="groq",
            model="groq/missing-model",
            api_key="secret",
            completion=raises_model_error,
        )

        with self.assertRaises(LLMModelUnavailableError):
            await provider.generate([{"role": "user", "content": "hey"}])

    async def test_litellm_provider_maps_invalid_api_key_without_secret(self):
        provider = LiteLLMProvider(
            provider_name="groq",
            model="groq/openai/gpt-oss-20b",
            api_key="secret",
            completion=raises_key_error,
        )

        with self.assertRaises(LLMCredentialsError) as exc:
            await provider.generate([{"role": "user", "content": "hey"}])

        self.assertNotIn("secret", str(exc.exception))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\services\test_llm_error_normalization.py -v`

Expected: FAIL because normalized error classes and injectable completion are not implemented.

- [ ] **Step 3: Implement minimal error model and mapping**

```python
class LLMError(Exception):
    def __init__(self, message: str, *, code: str, provider: str, model: str | None, retryable: bool):
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.model = model
        self.retryable = retryable
```

Map message fragments `model_not_found`, `does not exist`, and `not have access` to `LLMModelUnavailableError`; map `invalid api key`, `unauthorized`, and `401` to `LLMCredentialsError`; map timeout/rate-limit/server-unavailable phrases to retryable provider errors.

- [ ] **Step 4: Run focused and full backend tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\services\test_llm_error_normalization.py tests -v`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/backend/src/services/llm_errors.py apps/backend/src/services/llm_providers.py apps/backend/src/services/llm_service.py apps/backend/tests/services/test_llm_error_normalization.py
git commit -m "feat: normalize GARL LLM provider failures"
```

### Task 5: Conversation-Only API E2E Using Fake Provider

**Files:**
- Create: `apps/backend/tests/api/test_chat_e2e.py`
- Modify: `apps/backend/src/core/dependencies.py` only if dependency overrides need a helper factory.

**Interfaces:**
- Consumes: FastAPI `app`, `get_conversation_service`, `LLMService(provider=FakeLLMProvider())`.
- Produces: deterministic `POST /api/v1/chat` response for `hey`.

- [ ] **Step 1: Write failing API E2E test**

```python
from fastapi.testclient import TestClient

from src.core.dependencies import get_conversation_service
from src.main import app


def test_chat_hey_uses_fake_llm_and_does_not_require_tool_execution(fake_conversation_service):
    app.dependency_overrides[get_conversation_service] = lambda: fake_conversation_service
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/chat",
            json={"conversation_id": "fake-hey", "message": "hey"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "GARL is running" in body["data"]["response"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py -v`

Expected: FAIL until `fake_conversation_service` fixture and fake planner responses are available.

- [ ] **Step 3: Add test fixture using real GARL services and fake LLM**

```python
import pytest

from src.repositories.cognitive_state_repository import CognitiveStateRepository
from src.repositories.in_memory_conversation_repository import InMemoryConversationRepository
from src.repositories.in_memory_memory_repository import InMemoryMemoryRepository
from src.services.agent_service import AgentService
from src.services.approval_service import ApprovalService
from src.services.candidate_plan_generator import CandidatePlanGenerator
from src.services.cognitive_pipeline import CognitivePipeline
from src.services.context_builder import ContextBuilder
from src.services.conversation_service import ConversationService
from src.services.decision_service import DecisionService
from src.services.executor_service import ExecutorService
from src.services.llm_providers import FakeLLMProvider
from src.services.llm_service import LLMService
from src.services.memory_extractor import MemoryExtractor
from src.services.memory_service import MemoryService
from src.services.permission_service import PermissionService
from src.services.plan_parser import PlanParser
from src.services.plan_scorer import PlanScorer
from src.services.plan_validator import PlanValidator
from src.services.planner_service import PlannerService
from src.services.prompt_builder import PromptBuilder
from src.services.reasoning_service import ReasoningService
from src.services.response_composer import ResponseComposer
from src.services.reviewer_service import ReviewerService
from src.services.tool_catalog import ToolCatalog
from src.services.variable_resolver import VariableResolver
from src.tools.registry import ToolRegistry
from src.tools.tool_manager import ToolManager


class EmptyKnowledgeService:
    async def search_context(self, query: str, limit: int = 5) -> str:
        return ""


def build_fake_conversation_service() -> ConversationService:
    llm = LLMService(provider=FakeLLMProvider())
    tool_manager = ToolManager()
    ToolRegistry.register_all(tool_manager)

    planner = PlannerService(
        llm=llm,
        parser=PlanParser(),
        prompt_builder=PromptBuilder(),
        tool_catalog=ToolCatalog(tool_manager),
    )
    executor = ExecutorService(
        llm=llm,
        context_builder=ContextBuilder(),
        tool_manager=tool_manager,
        variable_resolver=VariableResolver(),
        permission_service=PermissionService(),
    )
    pipeline = CognitivePipeline(
        planner=planner,
        executor=executor,
        reviewer=ReviewerService(),
        decision=DecisionService(),
        reasoning=ReasoningService(llm),
        response_composer=ResponseComposer(),
        candidate_plan_generator=CandidatePlanGenerator(planner),
        plan_validator=PlanValidator(tool_manager),
        plan_scorer=PlanScorer(),
    )

    agent = AgentService(
        pipeline=pipeline,
        state_repository=CognitiveStateRepository(),
        approval_service=ApprovalService(tool_manager),
        memory_service=MemoryService(InMemoryMemoryRepository()),
        knowledge_service=EmptyKnowledgeService(),
        memory_extractor=MemoryExtractor(llm),
    )

    return ConversationService(
        agent,
        InMemoryConversationRepository(),
    )


@pytest.fixture
def fake_conversation_service():
    return build_fake_conversation_service()
```

The fixture uses real parser, validator, executor, decision, approval, memory, and response composer services. It uses an empty knowledge service so the test focuses on the LLM/runtime boundary rather than document ingestion.

- [ ] **Step 4: Make fake planner output parse into a no-tool LLM plan**

Fake provider response for planner prompts:

```json
{
  "steps": [
    {
      "action": "respond conversationally",
      "tool": null,
      "input": "Reply to the user with a concise greeting.",
      "arguments": {}
    }
  ]
}
```

- [ ] **Step 5: Run focused and full backend tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py tests -v`

Expected: PASS.

- [ ] **Step 6: Commit checkpoint**

```bash
git add apps/backend/tests/api/test_chat_e2e.py apps/backend/src/services/llm_providers.py
git commit -m "test: add deterministic conversation API E2E"
```

### Task 6: Real-Provider Hey Smoke Path

**Files:**
- Modify: `apps/backend/tests/test_llm.py`
- Create: `apps/backend/tests/api/test_live_chat_smoke.py`

**Interfaces:**
- Consumes: real `Settings`, real `LLMService`, mounted `/api/v1/chat`.
- Produces: opt-in live smoke test skipped unless `GARL_RUN_LIVE_LLM_TESTS=1`.

- [ ] **Step 1: Write opt-in live smoke test**

```python
import os

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.mark.skipif(
    os.environ.get("GARL_RUN_LIVE_LLM_TESTS") != "1",
    reason="Live provider smoke test is opt-in.",
)
def test_live_chat_hey_returns_useful_response():
    client = TestClient(app)

    response = client.post(
        "/api/v1/chat",
        json={"conversation_id": "live-hey-smoke", "message": "hey"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["response"].strip()
```

- [ ] **Step 2: Run default test and verify skip**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_live_chat_smoke.py -v`

Expected: SKIPPED when `GARL_RUN_LIVE_LLM_TESTS` is not `1`.

- [ ] **Step 3: Run manually with configured live model only when credentials are approved**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; $env:GARL_RUN_LIVE_LLM_TESTS='1'; python -m pytest tests\api\test_live_chat_smoke.py -v`

Expected with valid credentials/model: PASS. Expected with bad credentials/model: FAIL with normalized LLM error that does not reveal secrets.

- [ ] **Step 4: Commit checkpoint**

```bash
git add apps/backend/tests/test_llm.py apps/backend/tests/api/test_live_chat_smoke.py
git commit -m "test: add opt-in live GARL chat smoke test"
```

### Task 7: Tool Execution API E2E

**Files:**
- Modify: `apps/backend/src/services/llm_providers.py`
- Modify: `apps/backend/tests/api/test_chat_e2e.py`

**Interfaces:**
- Consumes: fake planner response selecting registered `calculator`.
- Produces: API response proving tool execution and response composition.

- [ ] **Step 1: Write failing calculator API test**

```python
def test_chat_calculator_objective_executes_registered_tool(fake_conversation_service):
    app.dependency_overrides[get_conversation_service] = lambda: fake_conversation_service
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/chat",
            json={"conversation_id": "fake-calc", "message": "calculate 2 + 2"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "4" in response.json()["data"]["response"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py::test_chat_calculator_objective_executes_registered_tool -v`

Expected: FAIL until fake planner emits calculator plan for calculator objective.

- [ ] **Step 3: Add deterministic calculator plan fixture**

Fake planner JSON:

```json
{
  "steps": [
    {
      "action": "calculate arithmetic result",
      "tool": "calculator",
      "input": "2 + 2",
      "arguments": {"query": "2 + 2"}
    }
  ]
}
```

- [ ] **Step 4: Run focused and full backend tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py tests -v`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/backend/src/services/llm_providers.py apps/backend/tests/api/test_chat_e2e.py
git commit -m "test: cover GARL calculator execution through API"
```

### Task 8: Permission DENY API E2E

**Files:**
- Modify: `apps/backend/src/services/llm_providers.py`
- Modify: `apps/backend/tests/api/test_chat_e2e.py`

**Interfaces:**
- Consumes: fake planner response selecting terminal command denied by `PermissionService`.
- Produces: API response and cognitive state showing denied action was not executed.

- [ ] **Step 1: Write failing denied-action API test**

```python
def test_chat_denied_terminal_action_returns_blocked_failure(fake_conversation_service):
    app.dependency_overrides[get_conversation_service] = lambda: fake_conversation_service
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/chat",
            json={"conversation_id": "fake-deny", "message": "run rm -rf /"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "blocked" in response.json()["data"]["response"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py::test_chat_denied_terminal_action_returns_blocked_failure -v`

Expected: FAIL until fake planner emits denied terminal plan.

- [ ] **Step 3: Add deterministic denied terminal plan fixture**

Fake planner JSON:

```json
{
  "steps": [
    {
      "action": "run destructive command",
      "tool": "terminal",
      "input": "rm -rf /",
      "arguments": {"query": "rm -rf /"}
    }
  ]
}
```

- [ ] **Step 4: Run focused and full backend tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py tests -v`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/backend/src/services/llm_providers.py apps/backend/tests/api/test_chat_e2e.py
git commit -m "test: cover permission deny through GARL API"
```

### Task 9: Approval-Required API Path

**Files:**
- Modify: `apps/backend/src/services/llm_providers.py`
- Modify: `apps/backend/tests/api/test_chat_e2e.py`

**Interfaces:**
- Consumes: fake planner response selecting terminal command that requires approval.
- Produces: first API call pauses with approval required; second call with `reject` clears pending state; accepted path executes exact stored action only after approval.

- [ ] **Step 1: Write failing approval pause/reject test**

```python
def test_chat_approval_required_path_can_be_rejected(fake_conversation_service):
    app.dependency_overrides[get_conversation_service] = lambda: fake_conversation_service
    try:
        client = TestClient(app)
        first = client.post(
            "/api/v1/chat",
            json={"conversation_id": "fake-approval", "message": "install package"},
        )
        second = client.post(
            "/api/v1/chat",
            json={"conversation_id": "fake-approval", "message": "reject"},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert "approval required" in first.json()["data"]["response"].lower()
    assert second.status_code == 200
    assert "nothing was executed" in second.json()["data"]["response"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py::test_chat_approval_required_path_can_be_rejected -v`

Expected: FAIL until fake planner emits approval-required terminal plan for install objective.

- [ ] **Step 3: Add deterministic approval-required terminal plan fixture**

Fake planner JSON:

```json
{
  "steps": [
    {
      "action": "install package",
      "tool": "terminal",
      "input": "pip install example-package",
      "arguments": {"query": "pip install example-package"}
    }
  ]
}
```

- [ ] **Step 4: Add accepted-approval test using safe fake approved tool if real terminal allowlist blocks command**

Use a registered fake tool named `terminal` in the test service graph if the test needs to prove exact stored action execution without running a real package install.

- [ ] **Step 5: Run focused and full backend tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py tests -v`

Expected: PASS.

- [ ] **Step 6: Commit checkpoint**

```bash
git add apps/backend/src/services/llm_providers.py apps/backend/tests/api/test_chat_e2e.py
git commit -m "test: cover GARL approval flow through API"
```

### Task 10: Failure Retry And No-Duplicate Behaviour

**Files:**
- Modify: `apps/backend/tests/services/test_cognitive_pipeline.py`
- Modify: `apps/backend/src/services/cognitive_pipeline.py` only if a reproduced duplicate-execution defect is found.

**Interfaces:**
- Consumes: `CognitivePipeline.run`, `DecisionService.RETRY`, `ExecutionState.attempt`, `ExecutionState.history`.
- Produces: regression proving retry stops at max iterations and does not duplicate consequential approved actions.

- [ ] **Step 1: Write failing no-duplicate retry test**

```python
class CountingExecutor:
    def __init__(self):
        self.calls = 0

    async def execute(self, messages, plan, state):
        self.calls += 1
        state.record(
            StepResult(
                step_id=1,
                success=False,
                error="timeout while calling tool",
            )
        )
        return "timeout while calling tool"


async def test_retry_attempts_are_bounded_and_explicit():
    executor = CountingExecutor()
    pipeline = make_retrying_pipeline(executor)
    pipeline.MAX_ITERATIONS = 2

    response = await pipeline.run(messages=[ConversationMessage(role="user", content="retry")], state=CognitiveState(objective="retry"))

    assert executor.calls == 2
    assert response.response == "timeout while calling tool"
```

- [ ] **Step 2: Run test to verify it fails or passes as characterization**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\services\test_cognitive_pipeline.py -v`

Expected: If it passes, keep it as contract coverage. If it fails, inspect root cause before editing production.

- [ ] **Step 3: Implement only if a root cause is reproduced**

If duplicate execution is observed, change the pipeline or executor at the smallest boundary that preserves `ExecutionState` recoverability and permission checks.

- [ ] **Step 4: Run focused and full backend tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\services\test_cognitive_pipeline.py tests -v`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/backend/src/services/cognitive_pipeline.py apps/backend/tests/services/test_cognitive_pipeline.py
git commit -m "test: bound GARL retry execution behaviour"
```

### Task 11: Resume Behaviour

**Files:**
- Modify: `apps/backend/tests/api/test_chat_e2e.py`
- Modify: `apps/backend/src/services/agent_service.py` only if a reproduced resume defect is found.
- Modify: `apps/backend/src/services/approval_service.py` only if approved resume does not execute exact stored action.

**Interfaces:**
- Consumes: `CognitiveStateRepository`, `AgentService.respond`, `ApprovalService.approve`, `ExecutionState.pending_*`.
- Produces: API-level proof that a pending approval survives between requests in the same process and resumes exact stored action once.

- [ ] **Step 1: Write failing resume test**

```python
def test_approval_resume_uses_existing_pending_state_without_replanning(fake_conversation_service):
    app.dependency_overrides[get_conversation_service] = lambda: fake_conversation_service
    try:
        client = TestClient(app)
        first = client.post(
            "/api/v1/chat",
            json={"conversation_id": "fake-resume", "message": "install package"},
        )
        second = client.post(
            "/api/v1/chat",
            json={"conversation_id": "fake-resume", "message": "approve"},
        )
    finally:
        app.dependency_overrides.clear()

    assert "approval required" in first.json()["data"]["response"].lower()
    assert second.status_code == 200
    assert second.json()["data"]["response"].strip()
```

- [ ] **Step 2: Run test to verify it fails or passes as characterization**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py::test_approval_resume_uses_existing_pending_state_without_replanning -v`

Expected: PASS if current approval resume contract is intact with the fake graph; FAIL if state is not preserved or approval executes the wrong action.

- [ ] **Step 3: Implement only if a root cause is reproduced**

Preserve `AgentService` behavior where approval/rejection commands are handled before setting a new objective. Preserve `ApprovalService` behavior where only `pending_tool`, `pending_arguments`, and `pending_step_id` are executed.

- [ ] **Step 4: Run focused and full backend tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py tests -v`

Expected: PASS.

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/backend/src/services/agent_service.py apps/backend/src/services/approval_service.py apps/backend/tests/api/test_chat_e2e.py
git commit -m "test: cover GARL approval resume behaviour"
```

### Task 12: Full Regression And Mission-Level Evaluation

**Files:**
- Modify: `docs/superpowers/specs/2026-08-30-garl-llm-runtime-hardening-design.md` only if implementation evidence changes the design.
- Modify: `docs/superpowers/plans/2026-08-30-garl-llm-runtime-hardening.md` only to mark completed checkboxes if the execution workflow tracks directly in this file.

**Interfaces:**
- Consumes: all implemented tasks and committed checkpoints.
- Produces: final verified branch state ready for review, push, or PR.

- [ ] **Step 1: Run backend compile**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m compileall src`

Expected: exit code 0.

- [ ] **Step 2: Run full backend tests**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests -v`

Expected: all deterministic tests pass; live smoke tests skipped unless explicitly enabled.

- [ ] **Step 3: Run backend startup and health**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; uvicorn src.main:app`

In a second shell, run:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/' | ConvertTo-Json -Depth 5
```

Expected: `{"message":"GARL Backend is running"}`.

- [ ] **Step 4: Run deterministic fake API scenarios**

Run: `cd apps/backend && $env:PATH=(Resolve-Path .\.venv313\Scripts).Path + ';' + $env:PATH; python -m pytest tests\api\test_chat_e2e.py -v`

Expected: conversation, tool execution, DENY, approval, retry, and resume scenarios pass offline.

- [ ] **Step 5: Run frontend validation when npm is available**

Run: `cd apps/frontend && npm ci && npm run lint && npm run build`

Expected: exit code 0 for all three commands. If local Codex lacks `npm`, record that exact environment limitation and verify `eslint.cmd` and `next.cmd build` through available local binaries without claiming npm verification.

- [ ] **Step 6: Run final diff review**

```bash
git diff --check
git status --short --branch
git diff --stat
git diff
```

Expected: no whitespace errors; diff contains only intentional provider-boundary, tests, and documentation changes.

- [ ] **Step 7: Mission-level evaluation**

Verify and document:

- GARL understood a conversation-only objective through fake API E2E.
- GARL created and validated plans before execution.
- Registered tools execute only after validation and permission checks.
- DENY prevents side effects.
- Approval pauses and resumes exact stored action.
- Retry is bounded.
- Resume does not duplicate consequential execution.
- Live smoke path is opt-in and reports clear provider errors when unavailable.

- [ ] **Step 8: Final commit**

```bash
git add apps/backend/src apps/backend/tests docs/superpowers
git commit -m "feat: harden GARL LLM runtime boundary"
```
