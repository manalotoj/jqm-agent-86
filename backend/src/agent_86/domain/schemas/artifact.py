from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateArtifactRequest(BaseModel):
    artifact_id: str
    filename: str = Field(min_length=1, max_length=512)
    content_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    blob_name: str = Field(min_length=1, max_length=1024)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactResponse(BaseModel):
    id: str
    session_id: str
    user_id: str
    filename: str
    content_type: str
    size_bytes: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime