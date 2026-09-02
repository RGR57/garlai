from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    capability_id: str
    name: str
    description: str
    tags: tuple[str, ...]
    required_tools: tuple[str, ...]
    optional_tools: tuple[str, ...]
    input_classes: tuple[str, ...]
    output_classes: tuple[str, ...]
    planner_guidance: str


@dataclass(frozen=True)
class CapabilityAvailability:
    capability: Capability
    available: bool
    missing_required_tools: tuple[str, ...]
