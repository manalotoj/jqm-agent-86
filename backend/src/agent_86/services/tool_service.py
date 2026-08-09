from agent_86.services.tool_guardrails import WebSearchGuardrails
from agent_86.tools.tool import ToolContext, ToolResult
from agent_86.tools.tool_registry import ToolRegistry


class ToolService:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        web_search_guardrails: WebSearchGuardrails | None = None,
    ) -> None:
        self._registry = registry
        self._web_search_guardrails = web_search_guardrails or WebSearchGuardrails()

    def list_tool_names(self) -> list[str]:
        return self._registry.list_names()

    async def execute_tools(
        self,
        tool_names: list[str],
        query: str,
        context: ToolContext,
    ) -> list[ToolResult]:
        results: list[ToolResult] = []

        for tool_name in tool_names:
            tool = self._registry.get(tool_name)
            if tool is None:
                continue

            blocked_result = self._web_search_guardrails.check(
                tool_name=tool_name,
                query=query,
                context=context,
            )
            if blocked_result is not None:
                results.append(blocked_result)
                continue

            result = await tool.execute(
                query=query,
                context=context,
            )
            results.append(result)

        return results