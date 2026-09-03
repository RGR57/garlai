from src.models.capability import Capability, CapabilityAvailability
from src.tools.tool_manager import ToolManager


class CapabilityRegistry:
    """Semantic capability metadata derived from active concrete tools."""

    _CAPABILITIES = (
        Capability(
            capability_id="calculation",
            name="Calculation",
            description="Evaluate arithmetic expressions using the calculator tool.",
            tags=("calculate", "calculation", "arithmetic", "math"),
            required_tools=("calculator",),
            optional_tools=(),
            input_classes=("expression",),
            output_classes=("calculation_result",),
            planner_guidance="Evaluate arithmetic with the calculator tool.",
        ),
        Capability(
            capability_id="software_engineering",
            name="Software engineering",
            description="Inspect, change, test, and verify software using existing tools.",
            tags=("software", "code", "prototype", "test", "build", "repository"),
            required_tools=("filesystem", "terminal"),
            optional_tools=("git",),
            input_classes=("objective", "workspace"),
            output_classes=("artifact", "verification_result"),
            planner_guidance=(
                "Inspect, change, test, and verify software using filesystem and "
                "terminal tools; use git when available."
            ),
        ),
        Capability(
            capability_id="web_research",
            name="Web research",
            description="Gather public web evidence with preserved source provenance.",
            tags=("research", "market", "competitor", "opportunity", "source", "evidence"),
            required_tools=("web_search",),
            optional_tools=("web_fetch",),
            input_classes=("objective", "query"),
            output_classes=("research_evidence",),
            planner_guidance=(
                "Gather public web evidence, preserve source URLs, and distinguish "
                "observed evidence from conclusions."
            ),
        ),
    )

    def __init__(self, tool_manager: ToolManager) -> None:
        self.tool_manager = tool_manager
        self._by_id = {
            capability.capability_id: capability
            for capability in self._CAPABILITIES
        }

    def list(self) -> tuple[Capability, ...]:
        return self._CAPABILITIES

    def get(self, capability_id: str) -> Capability | None:
        return self._by_id.get(capability_id)

    def availability(self, capability_id: str) -> CapabilityAvailability | None:
        capability = self.get(capability_id)
        if capability is None:
            return None
        missing = tuple(
            name for name in capability.required_tools
            if self.tool_manager.get(name) is None
        )
        return CapabilityAvailability(
            capability=capability,
            available=not missing,
            missing_required_tools=missing,
        )

    def available(self) -> tuple[CapabilityAvailability, ...]:
        return tuple(
            availability
            for capability in self._CAPABILITIES
            if (availability := self.availability(capability.capability_id)).available
        )

    def eligible_tool_names(self, capability_ids: tuple[str, ...]) -> tuple[str, ...]:
        names: list[str] = []
        for capability_id in capability_ids:
            availability = self.availability(capability_id)
            if availability is None or not availability.available:
                continue
            for name in (
                *availability.capability.required_tools,
                *availability.capability.optional_tools,
            ):
                if self.tool_manager.get(name) is not None and name not in names:
                    names.append(name)
        return tuple(names)

    def planner_description(self, capability_ids: tuple[str, ...]) -> str:
        lines = []
        for capability_id in capability_ids:
            availability = self.availability(capability_id)
            if availability is not None and availability.available:
                lines.append(
                    f"{availability.capability.capability_id}: "
                    f"{availability.capability.planner_guidance}"
                )
        return "\n".join(lines)
