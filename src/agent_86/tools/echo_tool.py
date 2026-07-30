from agent_86.tools.tool import ToolContext, ToolResult


class EchoTool:
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Returns the input query for testing tool plumbing."

    async def execute(
        self,
        query: str,
        context: ToolContext,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            content=f"Echo tool result: {query}",
            metadata={
                "session_id": context.session_id,
                "user_id": context.user_id,
            },
        )