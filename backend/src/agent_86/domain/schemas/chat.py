from typing import Any

from pydantic import BaseModel, Field

from backend.src.agent_86.domain.schemas.message import MessageResponse


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    message: MessageResponse


class ChatStreamEvent(BaseModel):
    event: str
    data: dict[str, Any] = Field(default_factory=dict)