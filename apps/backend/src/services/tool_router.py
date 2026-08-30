class ToolRouter:
    """
    Decides whether a request should use a tool.

    Future versions will use the LLM for routing.
    """

    TOOL_KEYWORDS = {
        "calculate": "calculator",
        "calculator": "calculator",
        "math": "calculator",
        "sum": "calculator",
        "multiply": "calculator",
    }

    async def select_tool(
        self,
        query: str,
    ) -> str | None:

        query = query.lower()

        for keyword, tool in self.TOOL_KEYWORDS.items():
            if keyword in query:
                return tool

        return None