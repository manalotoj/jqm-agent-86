from __future__ import annotations

import asyncio
from typing import Any

from agent_86.core.config import get_settings
from agent_86.mcp.adapter import Agent86McpAdapter
from agent_86.services.tool_guardrails import WebSearchGuardrails
from agent_86.services.tool_service import ToolService
from agent_86.tools.bootstrap import build_default_tool_registry

SERVER_NAME = "agent-86"
SERVER_VERSION = "0.1.0"
SERVER_TITLE = "agent-86 MCP Server"
SERVER_DESCRIPTION = "Expose agent-86 registered tools over MCP using stdio transport."


def _load_mcp_runtime() -> dict[str, Any]:
    try:
        from mcp.server.lowlevel import NotificationOptions, Server
        from mcp.server.models import InitializationOptions
        from mcp.server.stdio import stdio_server
        from mcp.types import CallToolResult, ListToolsResult, Tool as McpTool
    except ImportError as exc:  # pragma: no cover - exercised via runtime usage
        raise RuntimeError(
            "The optional MCP dependency is not installed. "
            "Install it with `pip install -r requirements-mcp.txt`."
        ) from exc

    return {
        "CallToolResult": CallToolResult,
        "InitializationOptions": InitializationOptions,
        "ListToolsResult": ListToolsResult,
        "McpTool": McpTool,
        "NotificationOptions": NotificationOptions,
        "Server": Server,
        "stdio_server": stdio_server,
    }


async def run_stdio_server() -> None:
    runtime = _load_mcp_runtime()

    registry = build_default_tool_registry()
    adapter = Agent86McpAdapter(
        registry=registry,
        tool_service=ToolService(
            registry,
            web_search_guardrails=WebSearchGuardrails.from_settings(get_settings()),
        ),
    )

    Server = runtime["Server"]
    McpTool = runtime["McpTool"]
    ListToolsResult = runtime["ListToolsResult"]
    CallToolResult = runtime["CallToolResult"]
    NotificationOptions = runtime["NotificationOptions"]
    InitializationOptions = runtime["InitializationOptions"]
    stdio_server = runtime["stdio_server"]

    async def on_list_tools(_context: Any, _params: Any) -> Any:
        return ListToolsResult(
            tools=[
                McpTool(
                    name=tool_payload["name"],
                    description=tool_payload["description"],
                    inputSchema=tool_payload["input_schema"],
                )
                for tool_payload in adapter.list_tools()
            ]
        )

    async def on_call_tool(_context: Any, params: Any) -> Any:
        result_payload = await adapter.call_tool(
            name=params.name,
            arguments=params.arguments,
        )
        return CallToolResult.model_validate(result_payload)

    server = Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        title=SERVER_TITLE,
        description=SERVER_DESCRIPTION,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )

    initialization_options = InitializationOptions(
        server_name=SERVER_NAME,
        server_version=SERVER_VERSION,
        title=SERVER_TITLE,
        description=SERVER_DESCRIPTION,
        capabilities=server.get_capabilities(NotificationOptions()),
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, initialization_options)


def main() -> None:
    try:
        asyncio.run(run_stdio_server())
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()