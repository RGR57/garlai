from src.services.capability_registry import CapabilityRegistry
from src.services.capability_resolver import CapabilityResolver
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
        raise AssertionError("Resolver tests must not execute tools.")


def _resolver(*tool_names: str) -> CapabilityResolver:
    manager = ToolManager()
    for name in tool_names:
        manager.register(NamedTool(name))
    return CapabilityResolver(CapabilityRegistry(manager))


def test_high_level_research_and_build_objective_selects_multiple_capabilities():
    selection = _resolver(
        "web_search", "web_fetch", "filesystem", "terminal", "git"
    ).resolve("Research a market opportunity and build a tested prototype.")

    assert selection.capability_ids == ("software_engineering", "web_research")
    assert selection.eligible_tool_names == (
        "filesystem", "terminal", "git", "web_search", "web_fetch"
    )


def test_hallucinated_or_malformed_proposals_cannot_expand_selection():
    selection = _resolver("web_search").resolve(
        "Research a market opportunity.",
        proposed_ids=("unknown", 3, "software_engineering"),
    )

    assert selection.capability_ids == ("web_research",)
    assert selection.eligible_tool_names == ("web_search",)
    assert selection.rejected_capability_ids == ("unknown", "3", "software_engineering")


def test_unavailable_capability_is_excluded_even_when_explicitly_proposed():
    selection = _resolver("web_search").resolve(
        "Build a local prototype.",
        proposed_ids=("software_engineering",),
    )

    assert selection.capability_ids == ()
    assert selection.unavailable_reasons == {
        "software_engineering": ("filesystem", "terminal")
    }
