from fastapi.testclient import TestClient
import pytest

from src.core.dependencies import get_conversation_service
from src.main import app
from src.repositories.cognitive_state_repository import CognitiveStateRepository
from src.repositories.in_memory_conversation_repository import (
    InMemoryConversationRepository,
)
from src.repositories.in_memory_memory_repository import (
    InMemoryMemoryRepository,
)
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

    return ConversationService(agent, InMemoryConversationRepository())


@pytest.fixture
def fake_conversation_service():
    return build_fake_conversation_service()


def test_chat_hey_uses_fake_llm_and_does_not_require_tool_execution(
    fake_conversation_service,
):
    app.dependency_overrides[get_conversation_service] = (
        lambda: fake_conversation_service
    )
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
    state = fake_conversation_service.agent.get_state("fake-hey")
    assert [result.tool for result in state.execution.history] == ["llm"]
