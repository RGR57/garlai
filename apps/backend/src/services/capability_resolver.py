from dataclasses import dataclass
import re
from typing import Any

from src.services.capability_registry import CapabilityRegistry


@dataclass(frozen=True)
class CapabilitySelection:
    capability_ids: tuple[str, ...]
    eligible_tool_names: tuple[str, ...]
    unavailable_reasons: dict[str, tuple[str, ...]]
    rejected_capability_ids: tuple[str, ...]


class CapabilityResolver:
    """Resolve semantic work classes before concrete planning begins."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def resolve(
        self,
        objective: str,
        *,
        proposed_ids: tuple[Any, ...] = (),
    ) -> CapabilitySelection:
        normalized_objective = set(re.findall(r"[a-z0-9_]+", objective.lower()))
        selected: list[str] = []
        unavailable: dict[str, tuple[str, ...]] = {}
        rejected: list[str] = []

        for capability in self.registry.list():
            if not normalized_objective.intersection(capability.tags):
                continue
            availability = self.registry.availability(capability.capability_id)
            if availability is not None and availability.available:
                selected.append(capability.capability_id)
            elif availability is not None:
                unavailable[capability.capability_id] = availability.missing_required_tools

        for proposed_id in proposed_ids:
            capability_id = str(proposed_id)
            availability = self.registry.availability(capability_id)
            if availability is None:
                rejected.append(capability_id)
                continue
            if not availability.available:
                unavailable[capability_id] = availability.missing_required_tools
                rejected.append(capability_id)
                continue
            if capability_id not in selected:
                selected.append(capability_id)

        selected_ids = tuple(
            capability.capability_id
            for capability in self.registry.list()
            if capability.capability_id in selected
        )
        return CapabilitySelection(
            capability_ids=selected_ids,
            eligible_tool_names=self.registry.eligible_tool_names(selected_ids),
            unavailable_reasons=unavailable,
            rejected_capability_ids=tuple(rejected),
        )
