import tempfile
import unittest
from pathlib import Path

from src.models.plan import ExecutionPlan, PlanStep
from src.models.execution_state import ExecutionState
from src.repositories.sqlite_durable_execution_repository import SQLiteDurableExecutionRepository
from src.services.context_builder import ContextBuilder
from src.services.durable_execution_service import DurableExecutionService
from src.services.executor_service import ExecutorService
from src.services.permission_service import PermissionService
from src.services.recovery_service import RecoveryService
from src.services.variable_resolver import VariableResolver
from src.tools.tool_manager import ToolManager
from src.tools.web_search_tool import WebSearchTool
from src.services.research_provider import FakeResearchProvider


class CountingResearchProvider(FakeResearchProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query: str, *, count: int = 5):
        self.calls += 1
        return await super().search(query, count=count)


class DurableResearchProvenanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_recovery_restores_untrusted_evidence_without_research_reexecution(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "research.sqlite3"
        repository = SQLiteDurableExecutionRepository(path)
        await repository.initialize()
        provider = CountingResearchProvider()
        tools = ToolManager()
        tools.register(WebSearchTool(provider))
        durable = DurableExecutionService(repository)
        run = await durable.start(
            objective="Research a market opportunity.", execution_context={"messages": []}, execution_id="research-run"
        )
        await durable.persist_validated_plan(
            run.execution_id,
            ExecutionPlan(steps=[PlanStep(id=1, action="research market", tool="web_search", input="GARL market", arguments={"query": "GARL market"})]),
        )
        executor = ExecutorService(
            llm=None, context_builder=ContextBuilder(), tool_manager=tools,
            variable_resolver=VariableResolver(), permission_service=PermissionService(), durable_repository=repository,
        )

        result = await executor.execute_ready_step(run.execution_id, 1, [], ExecutionState())
        restored = await RecoveryService(SQLiteDurableExecutionRepository(path)).prepare_resume(run.execution_id)

        self.assertTrue(result.success)
        self.assertEqual(provider.calls, 1)
        evidence = restored.execution_state.history[0].output["evidence"][0]
        self.assertEqual(restored.execution_state.history[0].output["trust"], "untrusted_external_evidence")
        self.assertEqual(evidence["url"], "https://example.test/garl-market")
        self.assertEqual(evidence["title"], "Deterministic GARL market evidence")
        self.assertEqual(evidence["query"], "GARL market")
        self.assertEqual(evidence["source"], "fake")
        self.assertEqual(evidence["retrieved_at"], "2026-09-02T00:00:00+00:00")
        self.assertEqual(provider.calls, 1)
