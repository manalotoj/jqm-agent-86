from typing import Any

from pydantic import BaseModel, Field

from agent_86.domain.schemas.message import MessageResponse


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        artifact_ids = self.metadata.get("artifact_ids")
        if artifact_ids is None:
            return

        if not isinstance(artifact_ids, list) or not all(
            isinstance(artifact_id, str) and artifact_id.strip()
            for artifact_id in artifact_ids
        ):
            raise ValueError("metadata.artifact_ids must be a list of non-empty strings")


class ChatResponse(BaseModel):
    message: MessageResponse


class ChatStreamEvent(BaseModel):
    event: str
    data: dict[str, Any] = Field(default_factory=dict)