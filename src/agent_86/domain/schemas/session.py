from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: str
    user_id: str
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime