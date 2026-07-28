from typing import Any

from pydantic import BaseModel, Field

from agent_86.domain.schemas.message import MessageResponse


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    message: MessageResponse