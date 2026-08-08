from backend.src.agent_86.tools.tool import Tool


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}

        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return [self._tools[name] for name in sorted(self._tools.keys())]

    def list_names(self) -> list[str]:
        return sorted(self._tools.keys())