import ast
import operator

from src.models.tool_result import ToolResult
from src.tools.base_tool import BaseTool


class CalculatorTool(BaseTool):

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return (
            "Safely evaluates arithmetic expressions. "
            "Use the 'query' argument for the mathematical "
            "expression, for example '847 * 39'."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Arithmetic expression to evaluate."
                    ),
                }
            },
            "required": [
                "query"
            ],
        }

    async def execute(
        self,
        query: str,
    ) -> ToolResult:

        expression = (
            query.lower()
            .replace("calculate", "")
            .replace("calculator", "")
            .replace("what is", "")
            .strip()
        )

        if not expression:

            return ToolResult(
                success=False,
                tool_name=self.name,
                output=None,
                metadata={
                    "error": (
                        "No arithmetic expression provided."
                    )
                },
            )

        try:

            result = self._evaluate(
                expression
            )

            return ToolResult(
                success=True,
                tool_name=self.name,
                output=result,
            )

        except Exception as exc:

            return ToolResult(
                success=False,
                tool_name=self.name,
                output=None,
                metadata={
                    "error": (
                        "Unable to calculate expression: "
                        f"{str(exc)}"
                    )
                },
            )

    def _evaluate(
        self,
        expression: str,
    ):

        operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        def eval_node(node):

            if isinstance(
                node,
                ast.Constant,
            ):

                if not isinstance(
                    node.value,
                    (int, float),
                ):
                    raise ValueError(
                        "Only numbers are allowed."
                    )

                return node.value

            if isinstance(
                node,
                ast.BinOp,
            ):

                operator_type = type(
                    node.op
                )

                if operator_type not in operators:
                    raise ValueError(
                        "Unsupported operator."
                    )

                return operators[
                    operator_type
                ](
                    eval_node(node.left),
                    eval_node(node.right),
                )

            if isinstance(
                node,
                ast.UnaryOp,
            ):

                operator_type = type(
                    node.op
                )

                if operator_type not in operators:
                    raise ValueError(
                        "Unsupported unary operator."
                    )

                return operators[
                    operator_type
                ](
                    eval_node(
                        node.operand
                    )
                )

            raise ValueError(
                "Unsupported expression."
            )

        tree = ast.parse(
            expression,
            mode="eval",
        )

        return eval_node(
            tree.body
        )