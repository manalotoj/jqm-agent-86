from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MessageRole = Literal["system", "user", "assistant"]


class CreateMessageRequest(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    id: str
    session_id: str
    user_id: str
    role: MessageRole
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime