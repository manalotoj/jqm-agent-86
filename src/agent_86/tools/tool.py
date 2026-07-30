from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolContext:
    session_id: str
    user_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    tool_name: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    async def execute(
        self,
        query: str,
        context: ToolContext,
    ) -> ToolResult: ...