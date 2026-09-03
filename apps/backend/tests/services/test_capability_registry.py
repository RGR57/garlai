from src.services.capability_registry import CapabilityRegistry
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
        return f"Test tool {self._name}."

    async def execute(self, **kwargs):
        raise AssertionError("Registry tests must not execute tools.")


def test_software_engineering_requires_filesystem_and_terminal():
    manager = ToolManager()
    manager.register(NamedTool("filesystem"))
    registry = CapabilityRegistry(manager)

    availability = registry.availability("software_engineering")

    assert not availability.available
    assert availability.missing_required_tools == ("terminal",)


def test_available_capability_exposes_only_registered_eligible_tools_in_stable_order():
    manager = ToolManager()
    for name in ("git", "terminal", "filesystem", "calculator"):
        manager.register(NamedTool(name))
    registry = CapabilityRegistry(manager)

    availability = registry.availability("software_engineering")

    assert availability.available
    assert registry.eligible_tool_names(("software_engineering",)) == (
        "filesystem",
        "terminal",
        "git",
    )
    assert registry.planner_description(("software_engineering",)) == (
        "software_engineering: Inspect, change, test, and verify software "
        "using filesystem and terminal tools; use git when available."
    )


def test_unknown_capability_is_not_eligible():
    registry = CapabilityRegistry(ToolManager())

    assert registry.availability("unknown") is None
    assert registry.eligible_tool_names(("unknown",)) == ()
