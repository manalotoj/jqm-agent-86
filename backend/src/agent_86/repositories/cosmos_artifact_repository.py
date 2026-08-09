from datetime import UTC, datetime

from azure.cosmos import ContainerProxy

from agent_86.domain.models.artifact import Artifact
from agent_86.domain.schemas.artifact import CreateArtifactRequest


class CosmosArtifactRepository:
    def __init__(self, container: ContainerProxy) -> None:
        self._container = container

    async def create_artifact(
        self,
        session_id: str,
        user_id: str,
        request: CreateArtifactRequest,
    ) -> Artifact:
        artifact = Artifact(
            id=request.artifact_id,
            session_id=session_id,
            user_id=user_id,
            filename=request.filename,
            content_type=request.content_type,
            size_bytes=request.size_bytes,
            blob_name=request.blob_name,
            metadata=request.metadata,
            created_at=datetime.now(UTC),
        )

        created = await self._container.create_item(self._to_document(artifact))
        return self._from_document(created)

    async def get_artifact(
        self,
        user_id: str,
        session_id: str,
        artifact_id: str,
    ) -> Artifact | None:
        query = """
        SELECT *
        FROM c
        WHERE c.id = @artifact_id AND c.session_id = @session_id AND c.user_id = @user_id
        """

        parameters = [
            {"name": "@artifact_id", "value": artifact_id},
            {"name": "@session_id", "value": session_id},
            {"name": "@user_id", "value": user_id},
        ]

        items = []
        async for item in self._container.query_items(
            query=query,
            parameters=parameters,
            partition_key=session_id,
        ):
            items.append(item)

        if not items:
            return None

        return self._from_document(items[0])

    async def list_artifacts(
        self,
        user_id: str,
        session_id: str,
    ) -> list[Artifact]:
        query = """
        SELECT *
        FROM c
        WHERE c.session_id = @session_id AND c.user_id = @user_id
        ORDER BY c.created_at ASC
        """

        parameters = [
            {"name": "@session_id", "value": session_id},
            {"name": "@user_id", "value": user_id},
        ]

        artifacts: list[Artifact] = []
        async for item in self._container.query_items(
            query=query,
            parameters=parameters,
            partition_key=session_id,
        ):
            artifacts.append(self._from_document(item))

        return artifacts

    async def delete_artifacts_for_session(
        self,
        user_id: str,
        session_id: str,
    ) -> list[Artifact]:
        artifacts = await self.list_artifacts(user_id, session_id)

        for artifact in artifacts:
            await self._container.delete_item(
                item=artifact.id,
                partition_key=session_id,
            )

        return artifacts

    def _to_document(self, artifact: Artifact) -> dict:
        return {
            "id": artifact.id,
            "session_id": artifact.session_id,
            "user_id": artifact.user_id,
            "filename": artifact.filename,
            "content_type": artifact.content_type,
            "size_bytes": artifact.size_bytes,
            "blob_name": artifact.blob_name,
            "metadata": artifact.metadata,
            "created_at": artifact.created_at.isoformat().replace("+00:00", "Z"),
        }

    def _from_document(self, document: dict) -> Artifact:
        return Artifact(
            id=document["id"],
            session_id=document["session_id"],
            user_id=document["user_id"],
            filename=document["filename"],
            content_type=document.get("content_type", "application/octet-stream"),
            size_bytes=int(document.get("size_bytes", 0)),
            blob_name=document["blob_name"],
            metadata=document.get("metadata", {}),
            created_at=self._parse_datetime(document["created_at"]),
        )

    def _parse_datetime(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))