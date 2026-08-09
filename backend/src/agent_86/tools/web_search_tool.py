import json

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

        result_metadata = {
            "session_id": context.session_id,
            "user_id": context.user_id,
            **metadata,
        }

        if self._should_emit_output_artifact(context.metadata):
            result_metadata["output_artifacts"] = [
                self._build_output_artifact_spec(query=query, content=content, metadata=metadata)
            ]

        return ToolResult(
            tool_name=self.name,
            content=content,
            metadata=result_metadata,
        )

    def _should_emit_output_artifact(self, context_metadata: dict[str, object]) -> bool:
        return bool(context_metadata.get("generate_search_artifact", False))

    def _build_output_artifact_spec(
        self,
        *,
        query: str,
        content: str,
        metadata: dict,
    ) -> dict[str, object]:
        provider = str(metadata.get("provider", "web-search")).strip() or "web-search"
        safe_provider = provider.replace(" ", "-")

        return {
            "filename": f"web-search-{safe_provider}-results.md",
            "content_type": "text/markdown",
            "content": self._build_artifact_markdown(query=query, content=content, metadata=metadata),
            "metadata": {
                "label": f"Web search results for: {query}",
                "tool_name": self.name,
                "provider": provider,
                "query": query,
                "result_count": metadata.get("result_count"),
                "status": metadata.get("status"),
            },
        }

    def _build_artifact_markdown(
        self,
        *,
        query: str,
        content: str,
        metadata: dict,
    ) -> str:
        front_matter = {
            "tool_name": self.name,
            "provider": metadata.get("provider"),
            "query": query,
            "status": metadata.get("status"),
            "result_count": metadata.get("result_count"),
        }

        return "\n".join(
            [
                "# Web Search Results",
                "",
                f"- Query: {query}",
                f"- Provider: {metadata.get('provider', 'unknown')}",
                f"- Status: {metadata.get('status', 'unknown')}",
                f"- Result count: {metadata.get('result_count', 0)}",
                "",
                "## Tool Metadata",
                "",
                "```json",
                json.dumps(front_matter, indent=2, sort_keys=True),
                "```",
                "",
                "## Formatted Results",
                "",
                content,
            ]
        )