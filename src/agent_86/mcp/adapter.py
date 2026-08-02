from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_86.services.tool_service import ToolService
from agent_86.tools.tool import ToolContext, ToolResult
from agent_86.tools.tool_registry import ToolRegistry

MCP_STDIO_SESSION_ID = "mcp-stdio"
MCP_STDIO_USER_ID = "mcp-client"
MCP_STDIO_METADATA = {
    "origin": "mcp",
    "transport": "stdio",
}


def build_mcp_tool_context() -> ToolContext:
    return ToolContext(
        session_id=MCP_STDIO_SESSION_ID,
        user_id=MCP_STDIO_USER_ID,
        metadata=dict(MCP_STDIO_METADATA),
    )


class Agent86McpAdapter:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        tool_service: ToolService,
        tool_context: ToolContext | None = None,
    ) -> None:
        self._registry = registry
        self._tool_service = tool_service
        self._tool_context = tool_context or build_mcp_tool_context()

    def list_tools(self) -> list[dict[str, Any]]:
        return [self._tool_to_mcp_payload(tool) for tool in self._registry.list_tools()]

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if arguments is None:
            return self._build_error_result(
                tool_name=name,
                message=f"Tool '{name}' requires an arguments object containing a 'query' field.",
            )

        query = arguments.get("query")
        if not isinstance(query, str):
            return self._build_error_result(
                tool_name=name,
                message=f"Tool '{name}' requires a string 'query' argument.",
            )

        tool_results = await self._tool_service.execute_tools(
            tool_names=[name],
            query=query,
            context=self._tool_context,
        )
        if not tool_results:
            return self._build_error_result(
                tool_name=name,
                message=f"Tool '{name}' is not registered.",
            )

        return self._build_success_result(tool_results[0])

    def _tool_to_mcp_payload(self, tool: Any) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }

    def _build_success_result(self, tool_result: ToolResult) -> dict[str, Any]:
        return {
            "content": [
                {
                    "type": "text",
                    "text": tool_result.content,
                }
            ],
            "structured_content": {
                "tool_name": tool_result.tool_name,
                "content": tool_result.content,
                "metadata": tool_result.metadata,
            },
            "is_error": False,
        }

    def _build_error_result(self, *, tool_name: str, message: str) -> dict[str, Any]:
        return {
            "content": [
                {
                    "type": "text",
                    "text": message,
                }
            ],
            "structured_content": {
                "tool_name": tool_name,
                "error": message,
            },
            "is_error": True,
        }