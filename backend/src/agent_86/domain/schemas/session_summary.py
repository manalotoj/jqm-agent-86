from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    description: str = Field(min_length=1)
    status: Literal["open", "done", "abandoned"]
    owner: str | None = None


class ArtifactRef(BaseModel):
    name: str = Field(min_length=1)
    artifact_type: Literal["docx", "pptx", "xlsx", "diagram", "code", "other"]
    location: str = Field(min_length=1)


class ChatSessionSummary(BaseModel):
    session_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    date_range_start: datetime
    date_range_end: datetime
    one_line_summary: str = Field(min_length=1)
    topics: list[str] = Field(default_factory=list)
    key_decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    artifacts_generated: list[ArtifactRef] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    continuation_context: str = Field(default="")


class SessionSummaryResponse(ChatSessionSummary):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime