from typing import Protocol

from agent_86.domain.models.artifact import Artifact
from agent_86.domain.schemas.artifact import CreateArtifactRequest


class ArtifactRepository(Protocol):
    async def create_artifact(
        self,
        session_id: str,
        user_id: str,
        request: CreateArtifactRequest,
    ) -> Artifact: ...

    async def get_artifact(
        self,
        user_id: str,
        session_id: str,
        artifact_id: str,
    ) -> Artifact | None: ...

    async def list_artifacts(
        self,
        user_id: str,
        session_id: str,
    ) -> list[Artifact]: ...

    async def delete_artifacts_for_session(
        self,
        user_id: str,
        session_id: str,
    ) -> list[Artifact]: ...