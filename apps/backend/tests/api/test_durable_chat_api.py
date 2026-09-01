import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.dependencies import (
    get_conversation_service,
    get_durable_execution_repository,
)
from src.main import app
from src.repositories.cognitive_state_repository import CognitiveStateRepository
from src.repositories.in_memory_conversation_repository import (
    InMemoryConversationRepository,
)
from src.repositories.in_memory_memory_repository import InMemoryMemoryRepository
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)
from src.services.agent_service import AgentService
from src.services.approval_service import ApprovalService
from src.services.candidate_plan_generator import CandidatePlanGenerator
from src.services.cognitive_pipeline import CognitivePipeline
from src.services.context_builder import ContextBuilder
from src.services.conversation_service import ConversationService
from src.services.decision_service import DecisionService
from src.services.durable_execution_service import DurableExecutionService
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
from src.tools.base_tool import BaseTool
from src.tools.tool_manager import ToolManager
from src.models.tool_result import ToolResult


class EmptyKnowledgeService:
    async def search_context(self, query: str, limit: int = 5) -> str:
        return ""


class RecordingTerminalTool(BaseTool):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    @property
    def name(self) -> str:
        return "terminal"

    @property
    def description(self) -> str:
        return "Records durable approval operations."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    async def execute(self, query: str) -> ToolResult:
        self.calls.append({"query": query})
        return ToolResult(success=True, tool_name=self.name, output="installed")


def build_durable_conversation_service(database_path: Path) -> ConversationService:
    repository = SQLiteDurableExecutionRepository(database_path)
    asyncio.run(repository.initialize())
    llm = LLMService(provider=FakeLLMProvider())
    tools = ToolManager()
    tools.register(RecordingTerminalTool())
    executor = ExecutorService(
        llm=llm,
        context_builder=ContextBuilder(),
        tool_manager=tools,
        variable_resolver=VariableResolver(),
        permission_service=PermissionService(),
        durable_repository=repository,
    )
    planner = PlannerService(
        llm=llm,
        parser=PlanParser(),
        prompt_builder=PromptBuilder(),
        tool_catalog=ToolCatalog(tools),
    )
    pipeline = CognitivePipeline(
        planner=planner,
        executor=executor,
        reviewer=ReviewerService(),
        decision=DecisionService(),
        reasoning=ReasoningService(llm),
        response_composer=ResponseComposer(),
        candidate_plan_generator=CandidatePlanGenerator(planner),
        plan_validator=PlanValidator(tools),
        plan_scorer=PlanScorer(),
    )
    agent = AgentService(
        pipeline=pipeline,
        state_repository=CognitiveStateRepository(),
        approval_service=ApprovalService(tools, repository, executor),
        memory_service=MemoryService(InMemoryMemoryRepository()),
        knowledge_service=EmptyKnowledgeService(),
        memory_extractor=MemoryExtractor(llm),
        durable_execution_service=DurableExecutionService(repository),
    )
    return ConversationService(agent, InMemoryConversationRepository())


def test_same_conversation_cannot_cross_approve_two_runs(tmp_path):
    service = build_durable_conversation_service(tmp_path / "runs.sqlite3")
    app.dependency_overrides[get_conversation_service] = lambda: service
    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/v1/chat",
                json={"conversation_id": "shared", "message": "install package"},
            )
            second = client.post(
                "/api/v1/chat",
                json={"conversation_id": "shared", "message": "install package"},
            )
            first_data = first.json()["data"]
            second_data = second.json()["data"]
            response = client.post(
                "/api/v1/chat",
                json={
                    "conversation_id": "shared",
                    "message": "approve",
                    "execution_id": first_data["execution_id"],
                    "approval_id": second_data["pending_approval_id"],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first_data["execution_id"] != second_data["execution_id"]
    assert response.status_code == 409


def test_lifespan_initializes_configured_durable_schema(tmp_path, monkeypatch):
    database_path = tmp_path / "runtime.sqlite3"
    monkeypatch.setattr(settings, "DURABLE_DB_PATH", str(database_path))
    get_durable_execution_repository.cache_clear()
    try:
        with TestClient(app):
            assert database_path.exists()
    finally:
        get_durable_execution_repository.cache_clear()
