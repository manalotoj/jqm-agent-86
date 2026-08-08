from agent_86.tools.tool import ToolContext, ToolResult
from agent_86.tools.tool_registry import ToolRegistry


class ToolService:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

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

            result = await tool.execute(
                query=query,
                context=context,
            )
            results.append(result)

        return results