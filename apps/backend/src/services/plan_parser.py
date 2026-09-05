import json
import re
from typing import Any

from src.models.plan import ExecutionPlan, PlanStep


class PlanParser:

    def parse(
        self,
        response: str,
    ) -> ExecutionPlan:

        data = self._parse_json(response)

        steps = data.get("steps")

        if not isinstance(steps, list):
            raise ValueError(
                "Execution plan 'steps' must be a list."
            )

        if not steps:
            raise ValueError(
                "Execution plan contains no steps."
            )

        plan = ExecutionPlan()

        for index, raw_step in enumerate(
            steps,
            start=1,
        ):

            if not isinstance(raw_step, dict):
                raise ValueError(
                    f"Plan step {index} must be an object."
                )

            action = raw_step.get(
                "action",
                "respond",
            )

            tool = raw_step.get(
                "tool",
                None,
            )

            step_input = raw_step.get(
                "input",
                "",
            )

            arguments = raw_step.get(
                "arguments",
                {},
            )

            result_contract = raw_step.get(
                "result_contract",
                None,
            )

            if not isinstance(action, str):
                raise ValueError(
                    f"Plan step {index} has invalid action."
                )

            # --------------------------------------------------
            # NORMALIZE LLM NULL VALUES
            # --------------------------------------------------
            #
            # Some models incorrectly return:
            #
            #     "tool": "null"
            #
            # instead of:
            #
            #     "tool": null
            #
            # Treat textual null values as actual Python None.
            #
            if isinstance(tool, str):

                normalized_tool = tool.strip().lower()

                if normalized_tool in {
                    "null",
                    "none",
                    "",
                }:

                    tool = None

            if tool is not None and not isinstance(
                tool,
                str,
            ):
                raise ValueError(
                    f"Plan step {index} has invalid tool."
                )

            if not isinstance(step_input, str):
                raise ValueError(
                    f"Plan step {index} has invalid input."
                )

            if result_contract is not None and not isinstance(result_contract, str):
                raise ValueError(
                    f"Plan step {index} has invalid result contract."
                )

            if arguments is None:
                arguments = {}

            if not isinstance(arguments, dict):
                raise ValueError(
                    f"Plan step {index} arguments "
                    "must be an object."
                )

            plan.add_step(
                PlanStep(
                    id=index,
                    action=action,
                    input=step_input,
                    tool=tool,
                    arguments=arguments,
                    result_contract=result_contract,
                )
            )

        return plan

    def _parse_json(
        self,
        response: str,
    ) -> dict[str, Any]:

        if not isinstance(response, str):
            raise ValueError(
                "Planner response must be a string."
            )

        cleaned = response.strip()

        # ------------------------------------------------------
        # REMOVE OPTIONAL MARKDOWN JSON FENCES
        # ------------------------------------------------------

        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

        try:

            data = json.loads(
                cleaned
            )

        except json.JSONDecodeError:

            # --------------------------------------------------
            # COMPATIBILITY FALLBACK
            # --------------------------------------------------

            match = re.search(
                r"\{.*\}",
                cleaned,
                re.DOTALL,
            )

            if not match:

                raise ValueError(
                    "Planner response does not "
                    "contain valid JSON."
                )

            try:

                data = json.loads(
                    match.group(0)
                )

            except json.JSONDecodeError as exc:

                raise ValueError(
                    "Invalid execution plan "
                    f"received from LLM:\n\n{response}"
                ) from exc

        if not isinstance(data, dict):

            raise ValueError(
                "Execution plan root must be an object."
            )

        return data
