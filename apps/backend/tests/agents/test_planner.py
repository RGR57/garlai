import pytest

from src.models.cognitive_state import CognitiveState
from src.services.plan_parser import PlanParser
from src.services.plan_validator import PlanValidator
from src.tools.calculator_tool import CalculatorTool
from src.tools.tool_manager import ToolManager


def parse_plan(response: str):
    return PlanParser().parse(response)


@pytest.mark.parametrize(
    "tool_value",
    [
        "null",
        "none",
        "",
    ],
)
def test_parser_normalizes_textual_empty_tool_values_to_no_tool(
    tool_value):
    plan = parse_plan(
        f"""
        {{
          "steps": [
            {{
              "action": "respond conversationally",
              "tool": "{tool_value}",
              "input": "say hello"
            }}
          ]
        }}
        """
    )

    assert plan.steps[0].tool is None


def test_parser_accepts_json_null_tool_as_no_tool():
    plan = parse_plan(
        """
        {
          "steps": [
            {
              "action": "respond conversationally",
              "tool": null,
              "input": "say hello"
            }
          ]
        }
        """
    )

    assert plan.steps[0].tool is None


def test_parser_accepts_markdown_fenced_json_plan():
    plan = parse_plan(
        """
        ```json
        {
          "steps": [
            {
              "action": "calculate result",
              "tool": "calculator",
              "input": "2 + 2",
              "arguments": {"query": "2 + 2"}
            }
          ]
        }
        ```
        """
    )

    assert plan.steps[0].tool == "calculator"
    assert plan.steps[0].arguments == {
        "query": "2 + 2",
    }


def test_parser_preserves_browser_result_contract_for_an_llm_step():
    plan = parse_plan(
        """
        {
          "steps": [
            {
              "action": "select the observed plan",
              "tool": null,
              "input": "{{step1}}",
              "arguments": {},
              "result_contract": "browser_target"
            }
          ]
        }
        """
    )

    assert plan.steps[0].result_contract == "browser_target"


def test_validator_rejects_unknown_or_tool_bound_result_contracts():
    manager = ToolManager()
    manager.register(CalculatorTool())
    validator = PlanValidator(manager)
    plan = parse_plan(
        """
        {
          "steps": [
            {
              "action": "calculate result",
              "tool": "calculator",
              "input": "2 + 2",
              "arguments": {"query": "2 + 2"},
              "result_contract": "browser_target"
            },
            {
              "action": "respond",
              "tool": null,
              "input": "hello",
              "arguments": {},
              "result_contract": "arbitrary_json"
            }
          ]
        }
        """
    )

    result = validator.validate(plan, CognitiveState(objective="calculate 2 + 2"))

    assert result.valid is False
    assert "only valid for tool-free" in result.errors[0]
    assert "unknown result contract" in result.errors[1]


def test_parser_rejects_malformed_json():
    with pytest.raises(
        ValueError,
        match="valid JSON|Invalid execution plan",
    ):
        parse_plan(
            '{"steps": [{"action": "respond", "tool": null}'
        )


def test_parser_rejects_empty_plan():
    with pytest.raises(
        ValueError,
        match="contains no steps",
    ):
        parse_plan('{"steps": []}')


def test_parser_rejects_malformed_arguments():
    with pytest.raises(
        ValueError,
        match="arguments must be an object",
    ):
        parse_plan(
            """
            {
              "steps": [
                {
                  "action": "calculate result",
                  "tool": "calculator",
                  "input": "2 + 2",
                  "arguments": "query=2+2"
                }
              ]
            }
            """
        )


def test_validator_accepts_registered_tool_with_valid_arguments():
    manager = ToolManager()
    manager.register(CalculatorTool())
    validator = PlanValidator(manager)
    plan = parse_plan(
        """
        {
          "steps": [
            {
              "action": "calculate result",
              "tool": "calculator",
              "input": "2 + 2",
              "arguments": {"query": "2 + 2"}
            }
          ]
        }
        """
    )

    result = validator.validate(
        plan,
        CognitiveState(objective="calculate 2 + 2"),
    )

    assert result.valid is True
    assert result.errors == []


def test_validator_rejects_unknown_tool():
    validator = PlanValidator(ToolManager())
    plan = parse_plan(
        """
        {
          "steps": [
            {
              "action": "search unsupported system",
              "tool": "unknown_tool",
              "input": "find records",
              "arguments": {"query": "records"}
            }
          ]
        }
        """
    )

    result = validator.validate(
        plan,
        CognitiveState(objective="find records"),
    )

    assert result.valid is False
    assert result.errors
    assert "unknown_tool" in result.errors[0]
