import hashlib
from datetime import UTC, datetime
from pathlib import Path

from agent_86.domain.models.artifact_analysis import ArtifactProcessingManifest
from agent_86.repositories.artifact_analysis_repository import ArtifactProcessingRepository
from agent_86.services.artifact_service import ArtifactService
from agent_86.services.blob_storage_service import BlobStorageService
from agent_86.services.csv_artifact_processor import CsvArtifactProcessor


class ArtifactProcessingService:
    """Produces durable, deterministic CSV derivatives for an owned artifact."""

    def __init__(
        self,
        artifact_service: ArtifactService,
        repository: ArtifactProcessingRepository,
        derived_blob_storage_service: BlobStorageService,
        csv_processor: CsvArtifactProcessor,
    ) -> None:
        self._artifact_service = artifact_service
        self._repository = repository
        self._derived_blob_storage_service = derived_blob_storage_service
        self._csv_processor = csv_processor

    async def process_artifact(
        self, *, user_id: str, session_id: str, artifact_id: str
    ) -> ArtifactProcessingManifest:
        artifact_with_content = await self._artifact_service.get_artifact_content(user_id, session_id, artifact_id)
        artifact = artifact_with_content.artifact
        source = artifact_with_content.download.content
        source_sha256 = hashlib.sha256(source).hexdigest()

        existing = await self._repository.get_manifest(user_id, session_id, artifact_id, source_sha256)
        if existing is not None and existing.state == "ready":
            return existing

        manifest = ArtifactProcessingManifest(
            id=f"{artifact_id}:{source_sha256}",
            session_id=session_id,
            user_id=user_id,
            artifact_id=artifact_id,
            source_sha256=source_sha256,
            state="processing",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        if not self._is_csv(artifact.filename, artifact.content_type):
            manifest.state = "unsupported"
            manifest.error_detail = "Whole-file processing currently supports CSV artifacts only"
            return await self._repository.upsert_manifest(manifest)

        try:
            result = self._csv_processor.process(source)
            prefix = f"derived/{session_id}/{artifact_id}/{result.source_sha256}"
            normalized_blob_name = f"{prefix}/normalized.jsonl"
            chunks_blob_name = f"{prefix}/chunks.jsonl"
            # chunks.jsonl is intentionally the canonical concatenation of all
            # deterministic chunks; their persisted ranges supply coverage proof.
            await self._derived_blob_storage_service.upload_blob(
                normalized_blob_name, result.normalized_jsonl, "application/x-ndjson"
            )
            await self._derived_blob_storage_service.upload_blob(
                chunks_blob_name, b"".join(chunk.jsonl for chunk in result.chunks), "application/x-ndjson"
            )
        except Exception as exc:
            manifest.state = "failed"
            manifest.error_detail = str(exc)
            manifest.updated_at = datetime.now(UTC)
            return await self._repository.upsert_manifest(manifest)

        manifest.state = "ready"
        manifest.headers = result.headers
        manifest.total_rows = result.total_rows
        manifest.chunk_count = len(result.chunks)
        manifest.chunk_row_ranges = [(chunk.start_row, chunk.end_row) for chunk in result.chunks]
        manifest.normalized_blob_name = normalized_blob_name
        manifest.chunks_blob_name = chunks_blob_name
        manifest.updated_at = datetime.now(UTC)
        return await self._repository.upsert_manifest(manifest)

    async def get_manifest(
        self, *, user_id: str, session_id: str, artifact_id: str
    ) -> ArtifactProcessingManifest | None:
        artifact_with_content = await self._artifact_service.get_artifact_content(user_id, session_id, artifact_id)
        source_sha256 = hashlib.sha256(artifact_with_content.download.content).hexdigest()
        return await self._repository.get_manifest(user_id, session_id, artifact_id, source_sha256)

    @staticmethod
    def _is_csv(filename: str, content_type: str) -> bool:
        return Path(filename).suffix.lower() == ".csv" or content_type.lower().split(";", 1)[0] in {
            "text/csv",
            "application/csv",
        }