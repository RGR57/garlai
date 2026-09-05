from dataclasses import dataclass, field
import re
from typing import Any

from src.models.cognitive_state import CognitiveState
from src.models.plan import ExecutionPlan, PlanStep
from src.tools.tool_manager import ToolManager


@dataclass
class ValidationResult:

    valid: bool

    errors: list[str] = field(
        default_factory=list
    )

    warnings: list[str] = field(
        default_factory=list
    )

    score: float = 0.0


class PlanValidator:

    VARIABLE_PATTERN = re.compile(
        r"\{\{step(\d+)\}\}"
    )

    RESULT_CONTRACTS = {
        "browser_target",
        "browser_verification",
    }

    def __init__(
        self,
        tool_manager: ToolManager,
    ):
        self.tool_manager = tool_manager

    def validate(
        self,
        plan: ExecutionPlan,
        state: CognitiveState,
        *,
        eligible_tool_names: tuple[str, ...] | None = None,
    ) -> ValidationResult:

        errors: list[str] = []
        warnings: list[str] = []

        if plan is None:
            return ValidationResult(
                valid=False,
                errors=[
                    "Execution plan is None."
                ],
                score=0.0,
            )

        if not isinstance(
            plan,
            ExecutionPlan,
        ):
            return ValidationResult(
                valid=False,
                errors=[
                    "Invalid execution plan type."
                ],
                score=0.0,
            )

        if not plan.steps:

            return ValidationResult(
                valid=False,
                errors=[
                    "Execution plan contains no steps."
                ],
                score=0.0,
            )

        self._validate_step_structure(
            plan,
            errors,
        )

        self._validate_step_ids(
            plan,
            errors,
        )

        self._validate_tools(
            plan,
            errors,
            eligible_tool_names,
        )

        self._validate_arguments(
            plan,
            errors,
        )

        self._validate_result_contracts(
            plan,
            errors,
        )

        self._validate_dependencies(
            plan,
            errors,
        )

        self._validate_duplicates(
            plan,
            warnings,
        )

        self._validate_unused_outputs(
            plan,
            warnings,
        )

        self._validate_objective(
            state,
            warnings,
        )

        valid = len(errors) == 0

        score = self._calculate_score(
            plan,
            errors,
            warnings,
        )

        return ValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            score=score,
        )

    # ==========================================================
    # STRUCTURE
    # ==========================================================

    def _validate_step_structure(
        self,
        plan: ExecutionPlan,
        errors: list[str],
    ) -> None:

        for step in plan.steps:

            if not isinstance(
                step,
                PlanStep,
            ):
                errors.append(
                    "Plan contains an invalid step object."
                )
                continue

            if not isinstance(
                step.id,
                int,
            ):
                errors.append(
                    f"Step ID must be an integer: "
                    f"{step.id}"
                )

            if not step.action or not step.action.strip():

                errors.append(
                    f"Step {step.id} has no action."
                )

            if step.input is None:

                errors.append(
                    f"Step {step.id} has invalid input."
                )

            if step.tool is not None:

                if not isinstance(
                    step.tool,
                    str,
                ):

                    errors.append(
                        f"Step {step.id} has an invalid "
                        f"tool name."
                    )

                elif not step.tool.strip():

                    errors.append(
                        f"Step {step.id} has an empty "
                        f"tool name."
                    )

            if not isinstance(
                step.arguments,
                dict,
            ):

                errors.append(
                    f"Step {step.id} arguments must "
                    f"be a dictionary."
                )

            if step.result_contract is not None and not isinstance(step.result_contract, str):
                errors.append(
                    f"Step {step.id} has an invalid result contract."
                )

    # ==========================================================
    # STEP IDS
    # ==========================================================

    def _validate_step_ids(
        self,
        plan: ExecutionPlan,
        errors: list[str],
    ) -> None:

        seen: set[int] = set()

        for step in plan.steps:

            if step.id in seen:

                errors.append(
                    f"Duplicate step ID detected: "
                    f"{step.id}"
                )

            seen.add(
                step.id
            )

    # ==========================================================
    # TOOLS
    # ==========================================================

    def _validate_tools(
        self,
        plan: ExecutionPlan,
        errors: list[str],
        eligible_tool_names: tuple[str, ...] | None,
    ) -> None:

        eligible_names = (
            set(eligible_tool_names)
            if eligible_tool_names is not None
            else None
        )

        for step in plan.steps:

            if step.tool is None:
                continue

            tool_name = step.tool.strip()

            if (
                eligible_names is not None
                and tool_name not in eligible_names
            ):
                errors.append(
                    f"Step {step.id}: tool '{tool_name}' is outside "
                    "the selected capabilities."
                )
                continue

            try:

                tool = self.tool_manager.get(
                    tool_name
                )

            except Exception as exc:

                errors.append(
                    f"Step {step.id}: unable to "
                    f"resolve tool '{tool_name}': "
                    f"{exc}"
                )

                continue

            if tool is None:

                errors.append(
                    f"Step {step.id}: tool "
                    f"'{tool_name}' not found."
                )

    # ==========================================================
    # ARGUMENTS
    # ==========================================================

    def _validate_arguments(
        self,
        plan: ExecutionPlan,
        errors: list[str],
    ) -> None:

        for step in plan.steps:

            if step.tool is None:
                continue

            arguments = step.arguments

            try:

                valid, error = (
                    self.tool_manager.validate_arguments(
                        step.tool,
                        arguments,
                        allow_variable_references=True,
                    )
                )

            except Exception as exc:

                errors.append(
                    f"Step {step.id}: argument "
                    f"validation failed: {exc}"
                )

                continue

            if not valid:

                errors.append(
                    f"Step {step.id}: invalid "
                    f"arguments: {error}"
                )

    # ==========================================================
    # DEPENDENCIES / VARIABLES
    # ==========================================================

    def _validate_dependencies(
        self,
        plan: ExecutionPlan,
        errors: list[str],
    ) -> None:

        completed_steps: set[int] = set()

        for step in plan.steps:

            references = []

            references.extend(
                self._extract_references(
                    step.input
                )
            )

            references.extend(
                self._extract_references(
                    step.arguments
                )
            )

            for referenced_step in references:

                if referenced_step not in completed_steps:

                    errors.append(
                        f"Step {step.id}: invalid "
                        f"reference {{step"
                        f"{referenced_step}}}. "
                        f"The referenced step has "
                        f"not executed yet."
                    )

            completed_steps.add(
                step.id
            )

    # ==========================================================
    # CONSTRAINED LLM OUTPUT
    # ==========================================================

    def _validate_result_contracts(
        self,
        plan: ExecutionPlan,
        errors: list[str],
    ) -> None:
        for step in plan.steps:
            if step.result_contract is None:
                continue
            if step.tool is not None:
                errors.append(
                    f"Step {step.id}: result contracts are only valid for tool-free LLM steps."
                )
            if step.result_contract not in self.RESULT_CONTRACTS:
                errors.append(
                    f"Step {step.id}: unknown result contract '{step.result_contract}'."
                )

    # ==========================================================
    # REFERENCE EXTRACTION
    # ==========================================================

    def _extract_references(
        self,
        value: Any,
    ) -> list[int]:

        references: list[int] = []

        if isinstance(
            value,
            str,
        ):

            matches = (
                self.VARIABLE_PATTERN.findall(
                    value
                )
            )

            references.extend(
                int(match)
                for match in matches
            )

            return references

        if isinstance(
            value,
            dict,
        ):

            for key, item in value.items():

                references.extend(
                    self._extract_references(
                        key
                    )
                )

                references.extend(
                    self._extract_references(
                        item
                    )
                )

            return references

        if isinstance(
            value,
            (list, tuple, set),
        ):

            for item in value:

                references.extend(
                    self._extract_references(
                        item
                    )
                )

        return references

    # ==========================================================
    # DUPLICATE WORK
    # ==========================================================

    def _validate_duplicates(
        self,
        plan: ExecutionPlan,
        warnings: list[str],
    ) -> None:

        seen: dict[str, int] = {}

        for step in plan.steps:

            signature = self._step_signature(
                step
            )

            if signature in seen:

                previous_step = seen[
                    signature
                ]

                warnings.append(
                    f"Step {step.id} appears to "
                    f"duplicate step "
                    f"{previous_step}."
                )

            else:

                seen[
                    signature
                ] = step.id

    # ==========================================================
    # UNUSED OUTPUTS
    # ==========================================================

    def _validate_unused_outputs(
        self,
        plan: ExecutionPlan,
        warnings: list[str],
    ) -> None:

        referenced_steps: set[int] = set()

        for step in plan.steps:

            references = []

            references.extend(
                self._extract_references(
                    step.input
                )
            )

            references.extend(
                self._extract_references(
                    step.arguments
                )
            )

            referenced_steps.update(
                references
            )

        last_step_id = plan.steps[-1].id

        for step in plan.steps:

            if step.id == last_step_id:
                continue

            if step.id not in referenced_steps:

                warnings.append(
                    f"Output of step {step.id} "
                    f"is not referenced by any "
                    f"later step."
                )

    # ==========================================================
    # OBJECTIVE
    # ==========================================================

    def _validate_objective(
        self,
        state: CognitiveState,
        warnings: list[str],
    ) -> None:

        if state is None:
            warnings.append(
                "Cognitive state is unavailable."
            )
            return

        objective = getattr(
            state,
            "objective",
            None,
        )

        if not objective:

            warnings.append(
                "Planner objective is empty."
            )

    # ==========================================================
    # SIGNATURE
    # ==========================================================

    def _step_signature(
        self,
        step: PlanStep,
    ) -> str:

        arguments = repr(
            sorted(
                step.arguments.items(),
                key=lambda item: str(
                    item[0]
                ),
            )
        )

        return "|".join(
            [
                step.action.strip().lower(),
                str(step.tool).strip().lower(),
                str(step.input).strip(),
                arguments,
                str(step.result_contract).strip(),
            ]
        )

    # ==========================================================
    # SCORE
    # ==========================================================

    def _calculate_score(
        self,
        plan: ExecutionPlan,
        errors: list[str],
        warnings: list[str],
    ) -> float:

        if errors:
            return 0.0

        score = 100.0

        score -= min(
            len(warnings) * 5.0,
            30.0,
        )

        if len(plan.steps) > 10:

            score -= min(
                (len(plan.steps) - 10) * 2.0,
                20.0,
            )

        return max(
            0.0,
            min(
                100.0,
                score,
            ),
        )
