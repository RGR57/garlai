from src.models.tool_result import ToolResult
from src.services.research_provider import ResearchProvider, ResearchProviderError
from src.tools.base_tool import BaseTool


class WebSearchTool(BaseTool):
    def __init__(self, provider: ResearchProvider) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search public web sources and return source-backed evidence."

    async def execute(self, query: str, count: int = 5) -> ToolResult:
        try:
            result = await self.provider.search(query, count=count)
        except ResearchProviderError as exc:
            return ToolResult(False, self.name, None, {"error": str(exc)})
        return ToolResult(
            True,
            self.name,
            {
                "query": result.query,
                "evidence": [
                    {
                        "title": item.title,
                        "url": item.url,
                        "snippet": item.snippet,
                        "source": item.source,
                    }
                    for item in result.evidence
                ],
            },
        )
