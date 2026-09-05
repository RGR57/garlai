import re
from typing import Any

from src.models.tool_result import ToolResult
from src.tools.base_tool import BaseTool, ToolInvocationContext, ToolPreflight


class ToolManager:

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(
        self,
        tool: BaseTool,
    ) -> None:

        if not tool.name:
            raise ValueError(
                "Tool must have a name."
            )

        self._tools[tool.name] = tool

    def get(
        self,
        name: str,
    ) -> BaseTool | None:

        return self._tools.get(name)

    def list_tools(
        self,
    ) -> list[BaseTool]:

        return list(self._tools.values())

    VARIABLE_REFERENCE = re.compile(r"^\{\{step\d+\}\}$")

    def validate_arguments(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        allow_variable_references: bool = False,
    ) -> tuple[bool, str | None]:

        tool = self.get(name)

        if tool is None:
            return (
                False,
                f"Tool '{name}' is not registered."
            )

        if not isinstance(arguments, dict):
            return (
                False,
                "Tool arguments must be an object."
            )

        schema = getattr(
            tool,
            "input_schema",
            None,
        )

        if not schema:
            return True, None

        properties = schema.get(
            "properties",
            {},
        )

        required = schema.get(
            "required",
            [],
        )

        # ------------------------------------------
        # REQUIRED ARGUMENTS
        # ------------------------------------------

        for field in required:

            if field not in arguments:
                return (
                    False,
                    (
                        f"Tool '{name}' requires "
                        f"argument '{field}'."
                    ),
                )

        # ------------------------------------------
        # UNKNOWN ARGUMENTS
        # ------------------------------------------

        for field in arguments:

            if field not in properties:
                return (
                    False,
                    (
                        f"Tool '{name}' received "
                        f"unknown argument '{field}'."
                    ),
                )

        # ------------------------------------------
        # BASIC TYPE VALIDATION
        # ------------------------------------------

        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "object": dict,
            "array": list,
        }

        for field, value in arguments.items():

            definition = properties.get(
                field,
                {},
            )

            expected_type = definition.get(
                "type"
            )

            python_type = type_map.get(
                expected_type
            )

            if (
                allow_variable_references
                and isinstance(value, str)
                and self.VARIABLE_REFERENCE.fullmatch(value)
            ):
                continue

            if (
                python_type is not None
                and not isinstance(
                    value,
                    python_type,
                )
            ):
                return (
                    False,
                    (
                        f"Tool '{name}' argument "
                        f"'{field}' must be "
                        f"{expected_type}."
                    ),
                )

            allowed_values = definition.get(
                "enum"
            )

            if (
                allowed_values is not None
                and value not in allowed_values
            ):
                return (
                    False,
                    (
                        f"Tool '{name}' argument "
                        f"'{field}' must be one of "
                        f"{allowed_values}."
                    ),
                )

        return True, None

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        invocation: ToolInvocationContext,
    ) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' is not registered.")
        return await tool.execute_with_context(arguments, invocation)

    async def preflight(
        self,
        name: str,
        arguments: dict[str, Any],
        invocation: ToolInvocationContext,
    ) -> ToolPreflight:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' is not registered.")
        return await tool.preflight(arguments, invocation)
