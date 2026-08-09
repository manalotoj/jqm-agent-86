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


class CreateGeneratedArtifactRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content_type: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)
    source_artifact_ids: list[str] = Field(default_factory=list)
    generated_by_message_id: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not all(isinstance(artifact_id, str) and artifact_id.strip() for artifact_id in self.source_artifact_ids):
            raise ValueError("source_artifact_ids must contain only non-empty strings")


class ArtifactResponse(BaseModel):
    id: str
    session_id: str
    user_id: str
    filename: str
    content_type: str
    size_bytes: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime