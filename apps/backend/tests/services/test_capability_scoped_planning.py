import asyncio

from src.models.cognitive_state import CognitiveState
from src.models.plan import ExecutionPlan, PlanStep
from src.services.plan_validator import PlanValidator
from src.services.plan_parser import PlanParser
from src.services.planner_service import PlannerService
from src.services.prompt_builder import PromptBuilder
from src.services.tool_catalog import ToolCatalog
from src.tools.base_tool import BaseTool
from src.tools.tool_manager import ToolManager


class NamedTool(BaseTool):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._name

    async def execute(self, **kwargs):
        raise AssertionError("Planning tests must not execute tools.")


def _manager() -> ToolManager:
    manager = ToolManager()
    for name in ("calculator", "web_search", "filesystem"):
        manager.register(NamedTool(name))
    return manager


def test_tool_catalog_only_serializes_eligible_registered_tools():
    definitions = ToolCatalog(_manager()).get_tool_definitions(
        eligible_tool_names=("web_search", "unknown_tool")
    )

    assert [definition["name"] for definition in definitions] == ["web_search"]


def test_validator_rejects_registered_tool_outside_capability_selection():
    validator = PlanValidator(_manager())
    plan = ExecutionPlan(
        steps=[
            PlanStep(
                id=1,
                action="calculate a result",
                tool="calculator",
                input="2 + 2",
                arguments={"query": "2 + 2"},
            )
        ]
    )

    result = validator.validate(
        plan,
        CognitiveState(objective="research a source"),
        eligible_tool_names=("web_search",),
    )

    assert result.valid is False
    assert "Step 1: tool 'calculator' is outside the selected capabilities." in result.errors


class RecordingLLM:
    def __init__(self) -> None:
        self.prompts: list[list[dict]] = []

    async def generate(self, prompt: list[dict]) -> str:
        self.prompts.append(prompt)
        return (
            '{"steps": [{"id": 1, "action": "search evidence", '
            '"tool": "web_search", "input": "market evidence", '
            '"arguments": {"query": "market evidence"}}]}'
        )


def test_planner_prompt_contains_only_capability_eligible_tools():
    llm = RecordingLLM()
    planner = PlannerService(
        llm=llm,
        parser=PlanParser(),
        prompt_builder=PromptBuilder(),
        tool_catalog=ToolCatalog(_manager()),
    )

    asyncio.run(
        planner.create_plan(
            messages=[],
            state=CognitiveState(objective="research a market"),
            eligible_tool_names=("web_search",),
            capability_guidance="web_research: preserve source URLs",
        )
    )

    system_prompt = llm.prompts[0][0]["content"]
    assert '"name": "web_search"' in system_prompt
    assert '"name": "calculator"' not in system_prompt
    assert '"name": "filesystem"' not in system_prompt
    assert "web_research: preserve source URLs" in system_prompt


def test_browser_only_catalog_does_not_expose_software_or_research_tools():
    manager = ToolManager()
    for name in ("browser_navigate", "browser_observe", "terminal", "web_search"):
        manager.register(NamedTool(name))

    definitions = ToolCatalog(manager).get_tool_definitions(
        eligible_tool_names=("browser_navigate", "browser_observe")
    )

    assert [definition["name"] for definition in definitions] == [
        "browser_navigate",
        "browser_observe",
    ]
