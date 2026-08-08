from agent_86.services.web_search_service import WebSearchService
from agent_86.tools.tool import ToolContext, ToolResult


class WebSearchTool:
    def __init__(self, web_search_service: WebSearchService) -> None:
        self._web_search_service = web_search_service

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Searches the web for the given query."

    @property
    def input_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The web search query to run.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        query: str,
        context: ToolContext,
    ) -> ToolResult:
        content, metadata = await self._web_search_service.search(query)

        return ToolResult(
            tool_name=self.name,
            content=content,
            metadata={
                "session_id": context.session_id,
                "user_id": context.user_id,
                **metadata,
            },
        )