from datetime import UTC, datetime
from inspect import isawaitable
from typing import Any

from azure.cosmos import ContainerProxy

from agent_86.domain.models.artifact_analysis import ArtifactAnalysisJob, ArtifactProcessingManifest


class _CosmosRepository:
    def __init__(self, container: ContainerProxy) -> None:
        self._container = container

    async def _get_container(self) -> Any:
        if isawaitable(self._container):
            self._container = await self._container
        return self._container

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class CosmosArtifactProcessingRepository(_CosmosRepository):
    async def get_manifest(self, user_id: str, session_id: str, artifact_id: str, source_sha256: str) -> ArtifactProcessingManifest | None:
        container = await self._get_container()
        query = "SELECT * FROM c WHERE c.artifact_id = @artifact_id AND c.source_sha256 = @source_sha256 AND c.user_id = @user_id"
        parameters = [
            {"name": "@artifact_id", "value": artifact_id},
            {"name": "@source_sha256", "value": source_sha256},
            {"name": "@user_id", "value": user_id},
        ]
        async for item in container.query_items(query=query, parameters=parameters, partition_key=session_id):
            return self._from_document(item)
        return None

    async def upsert_manifest(self, manifest: ArtifactProcessingManifest) -> ArtifactProcessingManifest:
        now = datetime.now(UTC)
        manifest.created_at = manifest.created_at or now
        manifest.updated_at = now
        container = await self._get_container()
        return self._from_document(await container.upsert_item(self._to_document(manifest)))

    def _to_document(self, manifest: ArtifactProcessingManifest) -> dict[str, Any]:
        return {
            **manifest.__dict__,
            "created_at": self._timestamp(manifest.created_at),
            "updated_at": self._timestamp(manifest.updated_at),
        }

    def _from_document(self, document: dict[str, Any]) -> ArtifactProcessingManifest:
        return ArtifactProcessingManifest(
            **{key: value for key, value in document.items() if key not in {"_rid", "_self", "_etag", "_attachments", "_ts", "created_at", "updated_at"}},
            created_at=self._parse_datetime(document["created_at"]),
            updated_at=self._parse_datetime(document["updated_at"]),
        )


class CosmosArtifactAnalysisJobRepository(_CosmosRepository):
    async def get_job(self, user_id: str, session_id: str, job_id: str) -> ArtifactAnalysisJob | None:
        container = await self._get_container()
        query = "SELECT * FROM c WHERE c.id = @id AND c.user_id = @user_id"
        parameters = [{"name": "@id", "value": job_id}, {"name": "@user_id", "value": user_id}]
        async for item in container.query_items(query=query, parameters=parameters, partition_key=session_id):
            return self._from_document(item)
        return None

    async def get_job_by_idempotency_key(self, user_id: str, session_id: str, artifact_id: str, source_sha256: str, analysis_type: str) -> ArtifactAnalysisJob | None:
        container = await self._get_container()
        query = "SELECT * FROM c WHERE c.artifact_id = @artifact_id AND c.source_sha256 = @source_sha256 AND c.analysis_type = @analysis_type AND c.user_id = @user_id"
        parameters = [
            {"name": "@artifact_id", "value": artifact_id}, {"name": "@source_sha256", "value": source_sha256},
            {"name": "@analysis_type", "value": analysis_type}, {"name": "@user_id", "value": user_id},
        ]
        async for item in container.query_items(query=query, parameters=parameters, partition_key=session_id):
            return self._from_document(item)
        return None

    async def upsert_job(self, job: ArtifactAnalysisJob) -> ArtifactAnalysisJob:
        now = datetime.now(UTC)
        job.created_at = job.created_at or now
        job.updated_at = now
        container = await self._get_container()
        return self._from_document(await container.upsert_item(self._to_document(job)))

    def _to_document(self, job: ArtifactAnalysisJob) -> dict[str, Any]:
        return {**job.__dict__, "created_at": self._timestamp(job.created_at), "updated_at": self._timestamp(job.updated_at)}

    def _from_document(self, document: dict[str, Any]) -> ArtifactAnalysisJob:
        return ArtifactAnalysisJob(
            **{key: value for key, value in document.items() if key not in {"_rid", "_self", "_etag", "_attachments", "_ts", "created_at", "updated_at"}},
            created_at=self._parse_datetime(document["created_at"]), updated_at=self._parse_datetime(document["updated_at"]),
        )