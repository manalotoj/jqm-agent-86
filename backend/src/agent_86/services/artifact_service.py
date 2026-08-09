from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from agent_86.domain.models.artifact import Artifact
from agent_86.domain.schemas.artifact import CreateArtifactRequest
from agent_86.repositories.artifact_repository import ArtifactRepository
from agent_86.services.blob_storage_service import BlobDownload, BlobStorageService


class ArtifactNotFoundError(Exception):
    def __init__(self, artifact_id: str, session_id: str) -> None:
        super().__init__(f"Artifact '{artifact_id}' not found in session '{session_id}'")
        self.artifact_id = artifact_id
        self.session_id = session_id


@dataclass(frozen=True)
class ArtifactWithContent:
    artifact: Artifact
    download: BlobDownload


class ArtifactService:
    def __init__(
        self,
        repository: ArtifactRepository,
        blob_storage_service: BlobStorageService,
    ) -> None:
        self._repository = repository
        self._blob_storage_service = blob_storage_service

    async def upload_artifact(
        self,
        *,
        session_id: str,
        user_id: str,
        filename: str,
        content_type: str,
        content: bytes,
        metadata: dict,
    ) -> Artifact:
        artifact_id = str(uuid4())
        resolved_filename = self._normalize_filename(filename)
        blob_name = f"sessions/{session_id}/artifacts/{artifact_id}/{resolved_filename}"

        await self._blob_storage_service.upload_blob(
            blob_name=blob_name,
            content=content,
            content_type=content_type,
        )

        try:
            return await self._repository.create_artifact(
                session_id=session_id,
                user_id=user_id,
                request=CreateArtifactRequest(
                    artifact_id=artifact_id,
                    filename=resolved_filename,
                    content_type=content_type,
                    size_bytes=len(content),
                    blob_name=blob_name,
                    metadata=metadata,
                ),
            )
        except Exception:
            await self._blob_storage_service.delete_blob(blob_name)
            raise

    async def get_artifact(
        self,
        user_id: str,
        session_id: str,
        artifact_id: str,
    ) -> Artifact | None:
        return await self._repository.get_artifact(user_id, session_id, artifact_id)

    async def list_artifacts(
        self,
        user_id: str,
        session_id: str,
    ) -> list[Artifact]:
        return await self._repository.list_artifacts(user_id, session_id)

    async def get_artifact_content(
        self,
        user_id: str,
        session_id: str,
        artifact_id: str,
    ) -> ArtifactWithContent:
        artifact = await self.get_artifact(user_id, session_id, artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(artifact_id, session_id)

        download = await self._blob_storage_service.download_blob(artifact.blob_name)
        return ArtifactWithContent(artifact=artifact, download=download)

    async def delete_artifacts_for_session(
        self,
        user_id: str,
        session_id: str,
    ) -> None:
        artifacts = await self._repository.delete_artifacts_for_session(user_id, session_id)
        for artifact in artifacts:
            await self._blob_storage_service.delete_blob(artifact.blob_name)

    async def validate_artifact_ids(
        self,
        user_id: str,
        session_id: str,
        artifact_ids: list[str],
    ) -> list[str]:
        seen: set[str] = set()
        normalized_ids: list[str] = []

        for artifact_id in artifact_ids:
            normalized_id = artifact_id.strip()
            if normalized_id in seen:
                continue

            artifact = await self.get_artifact(user_id, session_id, normalized_id)
            if artifact is None:
                raise ArtifactNotFoundError(normalized_id, session_id)

            seen.add(normalized_id)
            normalized_ids.append(normalized_id)

        return normalized_ids

    def _normalize_filename(self, filename: str) -> str:
        normalized = Path(filename).name.strip()
        if not normalized:
            return "artifact"
        return normalized[:512]