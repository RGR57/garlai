from dataclasses import dataclass, field
from typing import Any

from src.models.cognitive_state import CognitiveState
from src.models.plan import ExecutionPlan, PlanStep


@dataclass
class PlanScore:

    score: float

    breakdown: dict[str, float] = field(
        default_factory=dict
    )

    strengths: list[str] = field(
        default_factory=list
    )

    weaknesses: list[str] = field(
        default_factory=list
    )


class PlanScorer:

    def score(
        self,
        plan: ExecutionPlan,
        state: CognitiveState,
    ) -> PlanScore:

        if plan is None or not plan.steps:

            return PlanScore(
                score=0.0,
                breakdown={
                    "correctness": 0.0,
                    "safety": 0.0,
                    "execution_cost": 0.0,
                    "latency": 0.0,
                    "dependency_quality": 0.0,
                    "information_reuse": 0.0,
                    "complexity": 0.0,
                    "recoverability": 0.0,
                    "maintainability": 0.0,
                },
                weaknesses=[
                    "Plan is empty or unavailable."
                ],
            )

        correctness = self._score_correctness(
            plan
        )

        safety = self._score_safety(
            plan
        )

        execution_cost = self._score_execution_cost(
            plan
        )

        latency = self._score_latency(
            plan
        )

        dependency_quality = (
            self._score_dependency_quality(
                plan
            )
        )

        information_reuse = (
            self._score_information_reuse(
                plan
            )
        )

        complexity = self._score_complexity(
            plan
        )

        recoverability = (
            self._score_recoverability(
                plan
            )
        )

        maintainability = (
            self._score_maintainability(
                plan
            )
        )

        breakdown = {
            "correctness": correctness,
            "safety": safety,
            "execution_cost": execution_cost,
            "latency": latency,
            "dependency_quality": dependency_quality,
            "information_reuse": information_reuse,
            "complexity": complexity,
            "recoverability": recoverability,
            "maintainability": maintainability,
        }

        overall = (
            correctness * 0.25
            + safety * 0.15
            + execution_cost * 0.15
            + latency * 0.10
            + dependency_quality * 0.10
            + information_reuse * 0.10
            + complexity * 0.05
            + recoverability * 0.05
            + maintainability * 0.05
        )

        strengths, weaknesses = (
            self._build_feedback(
                breakdown
            )
        )

        return PlanScore(
            score=round(
                overall,
                2,
            ),
            breakdown=breakdown,
            strengths=strengths,
            weaknesses=weaknesses,
        )

    # ==========================================================
    # CORRECTNESS
    # ==========================================================

    def _score_correctness(
        self,
        plan: ExecutionPlan,
    ) -> float:

        if not plan.steps:
            return 0.0

        score = 100.0

        ids = [
            step.id
            for step in plan.steps
        ]

        if len(ids) != len(set(ids)):
            score -= 40.0

        for step in plan.steps:

            if not step.action.strip():
                score -= 20.0

            if step.tool is not None:
                if not step.tool.strip():
                    score -= 15.0

            if not isinstance(
                step.arguments,
                dict,
            ):
                score -= 20.0

        return self._clamp(
            score
        )

    # ==========================================================
    # SAFETY
    # ==========================================================

    def _score_safety(
        self,
        plan: ExecutionPlan,
    ) -> float:

        score = 100.0

        dangerous_actions = {
            "delete",
            "remove",
            "drop",
            "destroy",
            "overwrite",
            "terminate",
        }

        for step in plan.steps:

            text = (
                f"{step.action} "
                f"{step.tool or ''}"
            ).lower()

            for action in dangerous_actions:

                if action in text:

                    score -= 15.0

        return self._clamp(
            score
        )

    # ==========================================================
    # EXECUTION COST
    # ==========================================================

    def _score_execution_cost(
        self,
        plan: ExecutionPlan,
    ) -> float:

        step_count = len(
            plan.steps
        )

        tool_count = sum(
            1
            for step in plan.steps
            if step.tool is not None
        )

        llm_steps = sum(
            1
            for step in plan.steps
            if step.tool is None
        )

        score = 100.0

        score -= max(
            0,
            step_count - 3
        ) * 5.0

        score -= tool_count * 2.0

        score -= llm_steps * 3.0

        return self._clamp(
            score
        )

    # ==========================================================
    # LATENCY
    # ==========================================================

    def _score_latency(
        self,
        plan: ExecutionPlan,
    ) -> float:

        score = 100.0

        step_count = len(
            plan.steps
        )

        if step_count > 5:

            score -= (
                step_count - 5
            ) * 5.0

        return self._clamp(
            score
        )

    # ==========================================================
    # DEPENDENCY QUALITY
    # ==========================================================

    def _score_dependency_quality(
        self,
        plan: ExecutionPlan,
    ) -> float:

        score = 100.0

        for index, step in enumerate(
            plan.steps
        ):

            references = (
                self._extract_references(
                    step
                )
            )

            for reference in references:

                previous_ids = {
                    previous.id
                    for previous
                    in plan.steps[:index]
                }

                if reference not in previous_ids:

                    score -= 30.0

        return self._clamp(
            score
        )

    # ==========================================================
    # INFORMATION REUSE
    # ==========================================================

    def _score_information_reuse(
        self,
        plan: ExecutionPlan,
    ) -> float:

        if len(plan.steps) <= 1:
            return 100.0

        referenced_steps: set[int] = set()

        for step in plan.steps:

            referenced_steps.update(
                self._extract_references(
                    step
                )
            )

        if not referenced_steps:

            return 70.0

        useful_references = len(
            referenced_steps
        )

        score = 70.0 + min(
            useful_references * 5.0,
            30.0,
        )

        return self._clamp(
            score
        )

    # ==========================================================
    # COMPLEXITY
    # ==========================================================

    def _score_complexity(
        self,
        plan: ExecutionPlan,
    ) -> float:

        count = len(
            plan.steps
        )

        if count <= 2:
            return 100.0

        if count <= 4:
            return 90.0

        if count <= 6:
            return 80.0

        if count <= 8:
            return 65.0

        if count <= 10:
            return 50.0

        return 30.0

    # ==========================================================
    # RECOVERABILITY
    # ==========================================================

    def _score_recoverability(
        self,
        plan: ExecutionPlan,
    ) -> float:

        score = 100.0

        for step in plan.steps:

            action = (
                step.action
                .lower()
                .strip()
            )

            if any(
                keyword in action
                for keyword in [
                    "delete",
                    "destroy",
                    "drop",
                    "terminate",
                ]
            ):

                score -= 20.0

        if len(plan.steps) > 8:

            score -= 15.0

        return self._clamp(
            score
        )

    # ==========================================================
    # MAINTAINABILITY
    # ==========================================================

    def _score_maintainability(
        self,
        plan: ExecutionPlan,
    ) -> float:

        score = 100.0

        for step in plan.steps:

            if len(
                step.action
            ) > 200:

                score -= 5.0

            if len(
                step.input
            ) > 1000:

                score -= 5.0

        return self._clamp(
            score
        )

    # ==========================================================
    # REFERENCES
    # ==========================================================

    def _extract_references(
        self,
        step: PlanStep,
    ) -> set[int]:

        references: set[int] = set()

        values: list[Any] = [
            step.input,
            step.arguments,
        ]

        for value in values:

            references.update(
                self._extract_from_value(
                    value
                )
            )

        return references

    def _extract_from_value(
        self,
        value: Any,
    ) -> set[int]:

        references: set[int] = set()

        if isinstance(
            value,
            str,
        ):

            index = 0

            while True:

                start = value.find(
                    "{{step",
                    index,
                )

                if start == -1:
                    break

                end = value.find(
                    "}}",
                    start,
                )

                if end == -1:
                    break

                content = value[
                    start + 7:end
                ]

                try:

                    references.add(
                        int(content)
                    )

                except ValueError:
                    pass

                index = end + 2

            return references

        if isinstance(
            value,
            dict,
        ):

            for key, item in value.items():

                references.update(
                    self._extract_from_value(
                        key
                    )
                )

                references.update(
                    self._extract_from_value(
                        item
                    )
                )

            return references

        if isinstance(
            value,
            (list, tuple, set),
        ):

            for item in value:

                references.update(
                    self._extract_from_value(
                        item
                    )
                )

        return references

    # ==========================================================
    # FEEDBACK
    # ==========================================================

    def _build_feedback(
        self,
        breakdown: dict[str, float],
    ) -> tuple[
        list[str],
        list[str],
    ]:

        strengths: list[str] = []

        weaknesses: list[str] = []

        for category, value in breakdown.items():

            if value >= 90:

                strengths.append(
                    f"Strong {category.replace('_', ' ')}."
                )

            elif value < 60:

                weaknesses.append(
                    f"Weak {category.replace('_', ' ')}."
                )

        return (
            strengths,
            weaknesses,
        )

    # ==========================================================
    # CLAMP
    # ==========================================================

    def _clamp(
        self,
        value: float,
    ) -> float:

        return round(
            max(
                0.0,
                min(
                    100.0,
                    value,
                ),
            ),
            2,
        )