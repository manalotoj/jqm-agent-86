import json
from datetime import UTC, datetime

from agent_86.domain.models.artifact_analysis import ArtifactAnalysisJob
from agent_86.repositories.artifact_analysis_repository import ArtifactAnalysisJobRepository
from agent_86.services.artifact_processing_service import ArtifactProcessingService
from agent_86.services.blob_storage_service import BlobStorageService


ANALYSIS_TYPE_CSV_PROFILE = "csv_profile"


class ArtifactAnalysisService:
    """Executes the first explicit whole-file CSV analysis: a deterministic profile."""

    def __init__(
        self,
        processing_service: ArtifactProcessingService,
        repository: ArtifactAnalysisJobRepository,
        derived_blob_storage_service: BlobStorageService,
    ) -> None:
        self._processing_service = processing_service
        self._repository = repository
        self._derived_blob_storage_service = derived_blob_storage_service

    async def analyze_entire_file(
        self, *, user_id: str, session_id: str, artifact_id: str
    ) -> ArtifactAnalysisJob:
        manifest = await self._processing_service.process_artifact(
            user_id=user_id, session_id=session_id, artifact_id=artifact_id
        )
        job_id = f"{artifact_id}:{manifest.source_sha256}:{ANALYSIS_TYPE_CSV_PROFILE}"
        existing = await self._repository.get_job_by_idempotency_key(
            user_id, session_id, artifact_id, manifest.source_sha256, ANALYSIS_TYPE_CSV_PROFILE
        )
        if existing is not None and existing.state == "completed":
            return existing

        job = ArtifactAnalysisJob(
            id=job_id,
            session_id=session_id,
            user_id=user_id,
            artifact_id=artifact_id,
            source_sha256=manifest.source_sha256,
            analysis_type=ANALYSIS_TYPE_CSV_PROFILE,
            state="running",
            expected_rows=manifest.total_rows,
            expected_chunks=manifest.chunk_count,
            created_at=existing.created_at if existing is not None else datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        # Persist the running state before touching derived data so interrupted
        # executions are observable and retryable.
        job = await self._repository.upsert_job(job)
        if manifest.state != "ready" or manifest.normalized_blob_name is None:
            job.state = "failed"
            job.error_detail = manifest.error_detail or f"Artifact processing is {manifest.state}"
            return await self._repository.upsert_job(job)

        try:
            download = await self._derived_blob_storage_service.download_blob(manifest.normalized_blob_name)
            rows = [json.loads(line) for line in download.content.splitlines()]
            self._assert_complete_coverage(rows, manifest.total_rows, manifest.chunk_row_ranges)
            non_empty_by_column = {
                header: sum(bool(str(row["values"].get(header, "")).strip()) for row in rows)
                for header in manifest.headers
            }
        except Exception as exc:
            job.state = "failed"
            job.error_detail = str(exc)
            job.updated_at = datetime.now(UTC)
            return await self._repository.upsert_job(job)

        job.state = "completed"
        job.successful_rows = manifest.total_rows
        job.successful_chunks = manifest.chunk_count
        job.findings = {
            "analysis": "deterministic_csv_profile",
            "headers": manifest.headers,
            "row_count": manifest.total_rows,
            "non_empty_values_by_column": non_empty_by_column,
            "covered_row_ranges": manifest.chunk_row_ranges,
        }
        job.updated_at = datetime.now(UTC)
        return await self._repository.upsert_job(job)

    async def get_job(self, *, user_id: str, session_id: str, job_id: str) -> ArtifactAnalysisJob | None:
        return await self._repository.get_job(user_id, session_id, job_id)

    @staticmethod
    def _assert_complete_coverage(rows: list[dict], total_rows: int, ranges: list[tuple[int, int]]) -> None:
        source_rows = [row.get("source_row") for row in rows]
        if source_rows != list(range(1, total_rows + 1)):
            raise ValueError("Normalized CSV rows do not provide complete sequential coverage")
        covered_rows = [row for start, end in ranges for row in range(start, end + 1)]
        if covered_rows != source_rows:
            raise ValueError("Processing manifest chunk ranges do not provide complete row coverage")