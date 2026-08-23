import json
from datetime import UTC, datetime

from agent_86.domain.models.artifact_analysis import ArtifactAnalysisChunkResult, ArtifactAnalysisJob
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
        findings_inline_max_bytes: int = 64 * 1024,
    ) -> None:
        self._processing_service = processing_service
        self._repository = repository
        self._derived_blob_storage_service = derived_blob_storage_service
        self._findings_inline_max_bytes = findings_inline_max_bytes

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
        if manifest.state != "ready" or manifest.chunks_blob_name is None:
            job.state = "failed"
            job.error_detail = manifest.error_detail or f"Artifact processing is {manifest.state}"
            return await self._repository.upsert_job(job)

        try:
            download = await self._derived_blob_storage_service.download_blob(manifest.chunks_blob_name)
            rows = [json.loads(line) for line in download.content.splitlines()]
            self._assert_complete_coverage(rows, manifest.total_rows, manifest.chunk_row_ranges)
        except Exception as exc:
            job.state = "failed"
            job.error_detail = str(exc)
            job.updated_at = datetime.now(UTC)
            return await self._repository.upsert_job(job)

        existing_chunks = {
            result.chunk_index: result
            for result in await self._repository.list_chunk_results(user_id, session_id, job.id)
            if result.state == "completed"
        }
        offset = 0
        for chunk_index, (start_row, end_row) in enumerate(manifest.chunk_row_ranges):
            chunk_rows = rows[offset : offset + end_row - start_row + 1]
            offset += len(chunk_rows)
            if chunk_index in existing_chunks:
                continue
            try:
                if [row.get("source_row") for row in chunk_rows] != list(range(start_row, end_row + 1)):
                    raise ValueError("Chunk rows do not match the processing manifest row range")
                findings = {
                    "row_count": len(chunk_rows),
                    "non_empty_values_by_column": {
                        header: sum(bool(str(row["values"].get(header, "")).strip()) for row in chunk_rows)
                        for header in manifest.headers
                    },
                }
                result = ArtifactAnalysisChunkResult(
                    id=f"{job.id}:chunk:{chunk_index}", job_id=job.id, session_id=session_id, user_id=user_id,
                    artifact_id=artifact_id, chunk_index=chunk_index, start_row=start_row, end_row=end_row,
                    state="completed", findings=findings,
                )
            except Exception as exc:
                result = ArtifactAnalysisChunkResult(
                    id=f"{job.id}:chunk:{chunk_index}", job_id=job.id, session_id=session_id, user_id=user_id,
                    artifact_id=artifact_id, chunk_index=chunk_index, start_row=start_row, end_row=end_row,
                    state="failed", error_detail=str(exc),
                )
            await self._repository.upsert_chunk_result(result)

        chunk_results = await self._repository.list_chunk_results(user_id, session_id, job.id)
        completed = [result for result in chunk_results if result.state == "completed"]
        failed = [result for result in chunk_results if result.state == "failed"]
        job.successful_chunks = len(completed)
        job.failed_chunks = len(failed)
        job.successful_rows = sum(result.end_row - result.start_row + 1 for result in completed)
        job.failed_rows = sum(result.end_row - result.start_row + 1 for result in failed)
        non_empty_by_column = {
            header: sum(result.findings["non_empty_values_by_column"].get(header, 0) for result in completed)
            for header in manifest.headers
        }
        job.state = "completed" if len(completed) == manifest.chunk_count else "partial" if completed else "failed"
        job.error_detail = None if job.state == "completed" else "One or more analysis chunks failed"
        findings = {
            "analysis": "deterministic_csv_profile",
            "headers": manifest.headers,
            "row_count": job.successful_rows,
            "non_empty_values_by_column": non_empty_by_column,
            "covered_row_ranges": [(result.start_row, result.end_row) for result in completed],
        }
        findings_content = json.dumps(findings, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(findings_content) > self._findings_inline_max_bytes:
            job.findings_blob_name = (
                f"derived/{session_id}/{artifact_id}/{manifest.source_sha256}/analysis/{job.id}.json"
            )
            try:
                await self._derived_blob_storage_service.upload_blob(
                    job.findings_blob_name, findings_content, "application/json"
                )
            except Exception as exc:
                job.state = "failed"
                job.error_detail = f"Unable to store analysis findings: {exc}"
                job.updated_at = datetime.now(UTC)
                return await self._repository.upsert_job(job)
            job.findings = {
                "analysis": findings["analysis"],
                "row_count": findings["row_count"],
                "findings_stored_in_blob": True,
            }
        else:
            job.findings = findings
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