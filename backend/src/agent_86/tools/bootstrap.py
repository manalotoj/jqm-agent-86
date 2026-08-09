from __future__ import annotations

from typing import TYPE_CHECKING

from agent_86.core.config import get_settings
from agent_86.services.tool_guardrails import WebSearchGuardrails
from agent_86.services.tool_service import ToolService
from agent_86.tools.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from agent_86.services.web_search_service import WebSearchService


def build_default_tool_registry(
    *,
    web_search_service: WebSearchService | None = None,
) -> ToolRegistry:
    from agent_86.services.web_search_service import WebSearchService
    from agent_86.tools.web_search_tool import WebSearchTool

    settings = get_settings()
    resolved_web_search_service = web_search_service or WebSearchService(settings)

    return ToolRegistry(
        tools=[
            WebSearchTool(resolved_web_search_service),
        ]
    )


def build_default_tool_service(
    *,
    web_search_service: WebSearchService | None = None,
) -> ToolService:
    registry = build_default_tool_registry(web_search_service=web_search_service)
    return ToolService(
        registry,
        web_search_guardrails=WebSearchGuardrails.from_settings(get_settings()),
    )