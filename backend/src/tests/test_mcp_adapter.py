import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("COSMOS_ENDPOINT", "https://example.documents.azure.com:443/")
os.environ.setdefault("COSMOS_KEY", "test-cosmos-key")
os.environ.setdefault("FOUNDRY_OPENAI_BASE_URL", "https://example.openai.azure.com/")
os.environ.setdefault("FOUNDRY_DEFAULT_CHAT_MODEL", "gpt-4.1-mini")
os.environ.setdefault("FOUNDRY_PREMIUM_CHAT_MODEL", "gpt-5.4")

from backend.src.agent_86.mcp.adapter import Agent86McpAdapter
from backend.src.agent_86.services.tool_service import ToolService
from backend.src.agent_86.tools.tool import ToolContext, ToolResult
from backend.src.agent_86.tools.tool_registry import ToolRegistry
from backend.src.agent_86.tools.web_search_tool import WebSearchTool


class RecordingWebSearchService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str) -> tuple[str, dict]:
        self.queries.append(query)
        return (
            "Stubbed search results",
            {
                "provider": "stub",
                "query": query,
                "status": "ok",
            },
        )


def test_list_tools_returns_web_search_with_valid_input_schema():
    registry = ToolRegistry(
        tools=[
            WebSearchTool(RecordingWebSearchService()),
        ]
    )
    adapter = Agent86McpAdapter(
        registry=registry,
        tool_service=ToolService(registry),
    )

    tools = adapter.list_tools()

    assert len(tools) == 1
    assert tools[0]["name"] == "web_search"
    assert tools[0]["description"] == "Searches the web for the given query."
    assert tools[0]["input_schema"] == {
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


@pytest.mark.asyncio
async def test_call_tool_delegates_to_tool_service_and_returns_mcp_result_shape():
    web_search_service = RecordingWebSearchService()
    registry = ToolRegistry(
        tools=[
            WebSearchTool(web_search_service),
        ]
    )
    real_tool_service = ToolService(registry)
    tool_service = SimpleNamespace(
        execute_tools=AsyncMock(side_effect=real_tool_service.execute_tools)
    )
    adapter = Agent86McpAdapter(
        registry=registry,
        tool_service=tool_service,
    )

    result = await adapter.call_tool(
        name="web_search",
        arguments={"query": "latest ai news"},
    )

    tool_service.execute_tools.assert_awaited_once_with(
        tool_names=["web_search"],
        query="latest ai news",
        context=ToolContext(
            session_id="mcp-stdio",
            user_id="mcp-client",
            metadata={"origin": "mcp", "transport": "stdio"},
        ),
    )
    assert web_search_service.queries == ["latest ai news"]
    assert result == {
        "content": [
            {
                "type": "text",
                "text": "Stubbed search results",
            }
        ],
        "structured_content": {
            "tool_name": "web_search",
            "content": "Stubbed search results",
            "metadata": {
                "session_id": "mcp-stdio",
                "user_id": "mcp-client",
                "provider": "stub",
                "query": "latest ai news",
                "status": "ok",
            },
        },
        "is_error": False,
    }


@pytest.mark.asyncio
async def test_call_tool_returns_mcp_error_shape_for_missing_query_argument():
    tool_service = SimpleNamespace(
        execute_tools=AsyncMock(
            return_value=[
                ToolResult(
                    tool_name="web_search",
                    content="should not run",
                    metadata={},
                )
            ]
        )
    )
    adapter = Agent86McpAdapter(
        registry=ToolRegistry(),
        tool_service=tool_service,
    )

    result = await adapter.call_tool(name="web_search", arguments={})

    tool_service.execute_tools.assert_not_called()
    assert result == {
        "content": [
            {
                "type": "text",
                "text": "Tool 'web_search' requires a string 'query' argument.",
            }
        ],
        "structured_content": {
            "tool_name": "web_search",
            "error": "Tool 'web_search' requires a string 'query' argument.",
        },
        "is_error": True,
    }


def test_server_module_import_does_not_require_optional_mcp_dependency():
    import backend.src.agent_86.mcp.server as server_module

    assert callable(server_module.main)