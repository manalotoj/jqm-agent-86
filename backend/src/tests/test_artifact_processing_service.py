import pytest

from agent_86.domain.models.artifact import Artifact
from agent_86.services.artifact_analysis_service import ArtifactAnalysisService
from agent_86.services.artifact_processing_service import ArtifactProcessingService
from agent_86.services.artifact_service import ArtifactWithContent
from agent_86.services.blob_storage_service import BlobDownload
from agent_86.services.csv_artifact_processor import CsvArtifactProcessor


class StubArtifactService:
    def __init__(self, filename: str, content_type: str, content: bytes) -> None:
        self.result = ArtifactWithContent(
            artifact=Artifact("artifact-1", "session-1", "user-1", filename, content_type, len(content), "source"),
            download=BlobDownload(content, content_type),
        )

    async def get_artifact_content(self, user_id: str, session_id: str, artifact_id: str) -> ArtifactWithContent:
        assert (user_id, session_id, artifact_id) == ("user-1", "session-1", "artifact-1")
        return self.result


class InMemoryManifestRepository:
    def __init__(self) -> None:
        self.items = {}

    async def get_manifest(self, user_id, session_id, artifact_id, source_sha256):
        return self.items.get((user_id, session_id, artifact_id, source_sha256))

    async def upsert_manifest(self, manifest):
        self.items[(manifest.user_id, manifest.session_id, manifest.artifact_id, manifest.source_sha256)] = manifest
        return manifest


class InMemoryBlobStorage:
    def __init__(self) -> None:
        self.items = {}

    async def upload_blob(self, blob_name, content, content_type):
        self.items[blob_name] = BlobDownload(content, content_type)

    async def download_blob(self, blob_name):
        return self.items[blob_name]


class FailingBlobStorage:
    async def upload_blob(self, blob_name, content, content_type):
        raise RuntimeError("derived storage unavailable")


class InMemoryAnalysisJobRepository:
    def __init__(self) -> None:
        self.items = {}
        self.chunk_results = {}
        self.upserted_states = []

    async def get_job(self, user_id, session_id, job_id):
        return self.items.get((user_id, session_id, job_id))

    async def get_job_by_idempotency_key(self, user_id, session_id, artifact_id, source_sha256, analysis_type):
        return next(
            (
                job
                for job in self.items.values()
                if (job.user_id, job.session_id, job.artifact_id, job.source_sha256, job.analysis_type)
                == (user_id, session_id, artifact_id, source_sha256, analysis_type)
            ),
            None,
        )

    async def upsert_job(self, job):
        self.upserted_states.append(job.state)
        self.items[(job.user_id, job.session_id, job.id)] = job
        return job

    async def list_chunk_results(self, user_id, session_id, job_id):
        return sorted(
            [result for (owner, session, result_job_id, _), result in self.chunk_results.items()
             if (owner, session, result_job_id) == (user_id, session_id, job_id)],
            key=lambda result: result.chunk_index,
        )

    async def upsert_chunk_result(self, result):
        self.chunk_results[(result.user_id, result.session_id, result.job_id, result.chunk_index)] = result
        return result


class FailingAnalysisDownloadStorage(InMemoryBlobStorage):
    async def download_blob(self, blob_name):
        raise RuntimeError("derived analysis data unavailable")


class FailingAnalysisFindingsStorage(InMemoryBlobStorage):
    async def upload_blob(self, blob_name, content, content_type):
        if "/analysis/" in blob_name:
            raise RuntimeError("analysis findings storage unavailable")
        await super().upload_blob(blob_name, content, content_type)


@pytest.mark.asyncio
async def test_process_csv_writes_derived_blobs_with_complete_row_ranges() -> None:
    repository = InMemoryManifestRepository()
    derived = InMemoryBlobStorage()
    service = ArtifactProcessingService(
        StubArtifactService("portfolio.csv", "text/csv", b"symbol,quantity\nMSFT,10\nAAPL,20\nNVDA,30\n"),
        repository,
        derived,
        CsvArtifactProcessor(max_rows=10, chunk_rows=2),
    )

    manifest = await service.process_artifact(user_id="user-1", session_id="session-1", artifact_id="artifact-1")

    assert manifest.state == "ready"
    assert manifest.total_rows == 3
    assert manifest.chunk_row_ranges == [(1, 2), (3, 3)]
    assert manifest.normalized_blob_name in derived.items
    assert manifest.chunks_blob_name in derived.items
    assert await service.process_artifact(user_id="user-1", session_id="session-1", artifact_id="artifact-1") is manifest


@pytest.mark.asyncio
async def test_process_non_csv_returns_unsupported_manifest_without_writing_blobs() -> None:
    derived = InMemoryBlobStorage()
    service = ArtifactProcessingService(
        StubArtifactService("notes.txt", "text/plain", b"not a csv"),
        InMemoryManifestRepository(),
        derived,
        CsvArtifactProcessor(max_rows=10, chunk_rows=2),
    )

    manifest = await service.process_artifact(user_id="user-1", session_id="session-1", artifact_id="artifact-1")

    assert manifest.state == "unsupported"
    assert derived.items == {}


@pytest.mark.asyncio
async def test_process_csv_records_a_failed_manifest_when_derived_storage_fails() -> None:
    service = ArtifactProcessingService(
        StubArtifactService("portfolio.csv", "text/csv", b"symbol\nMSFT\n"),
        InMemoryManifestRepository(),
        FailingBlobStorage(),
        CsvArtifactProcessor(max_rows=10, chunk_rows=2),
    )

    manifest = await service.process_artifact(user_id="user-1", session_id="session-1", artifact_id="artifact-1")

    assert manifest.state == "failed"
    assert manifest.error_detail == "derived storage unavailable"
    assert manifest.created_at is not None
    assert manifest.updated_at is not None


@pytest.mark.asyncio
async def test_analysis_persists_running_then_failed_when_derived_download_fails() -> None:
    derived = FailingAnalysisDownloadStorage()
    processing = ArtifactProcessingService(
        StubArtifactService("portfolio.csv", "text/csv", b"symbol\nMSFT\n"),
        InMemoryManifestRepository(),
        derived,
        CsvArtifactProcessor(max_rows=10, chunk_rows=2),
    )
    repository = InMemoryAnalysisJobRepository()
    service = ArtifactAnalysisService(processing, repository, derived)

    job = await service.analyze_entire_file(user_id="user-1", session_id="session-1", artifact_id="artifact-1")

    assert job.state == "failed"
    assert job.error_detail == "derived analysis data unavailable"
    assert repository.upserted_states == ["running", "failed"]
    assert job.expected_rows == 1
    assert job.expected_chunks == 1


@pytest.mark.asyncio
async def test_analysis_retries_only_failed_chunks_and_transitions_partial_to_completed() -> None:
    derived = InMemoryBlobStorage()
    processing = ArtifactProcessingService(
        StubArtifactService("portfolio.csv", "text/csv", b"symbol\nMSFT\nAAPL\nNVDA\n"),
        InMemoryManifestRepository(),
        derived,
        CsvArtifactProcessor(max_rows=10, chunk_rows=2),
    )
    manifest = await processing.process_artifact(user_id="user-1", session_id="session-1", artifact_id="artifact-1")
    # Keep the first chunk valid while making the second chunk fail profiling.
    derived.items[manifest.chunks_blob_name] = BlobDownload(
        b'{"source_row":1,"values":{"symbol":"MSFT"}}\n'
        b'{"source_row":2,"values":{"symbol":"AAPL"}}\n'
        b'{"source_row":3,"values":"invalid"}\n',
        "application/x-ndjson",
    )
    repository = InMemoryAnalysisJobRepository()
    service = ArtifactAnalysisService(processing, repository, derived)

    partial = await service.analyze_entire_file(user_id="user-1", session_id="session-1", artifact_id="artifact-1")
    first_chunk = next(iter(repository.chunk_results.values()))
    derived.items[manifest.chunks_blob_name] = BlobDownload(
        b'{"source_row":1,"values":{"symbol":"MSFT"}}\n'
        b'{"source_row":2,"values":{"symbol":"AAPL"}}\n'
        b'{"source_row":3,"values":{"symbol":"NVDA"}}\n',
        "application/x-ndjson",
    )
    completed = await service.analyze_entire_file(user_id="user-1", session_id="session-1", artifact_id="artifact-1")

    assert partial.state == "partial"
    assert (partial.successful_chunks, partial.failed_chunks) == (1, 1)
    assert completed.state == "completed"
    assert (completed.successful_rows, completed.failed_rows) == (3, 0)
    assert repository.chunk_results[("user-1", "session-1", completed.id, 0)] is first_chunk


@pytest.mark.asyncio
async def test_analysis_stores_oversized_findings_in_derived_blob() -> None:
    derived = InMemoryBlobStorage()
    processing = ArtifactProcessingService(
        StubArtifactService("portfolio.csv", "text/csv", b"symbol\nMSFT\n"), InMemoryManifestRepository(), derived,
        CsvArtifactProcessor(max_rows=10, chunk_rows=1),
    )
    service = ArtifactAnalysisService(processing, InMemoryAnalysisJobRepository(), derived, findings_inline_max_bytes=1)

    job = await service.analyze_entire_file(user_id="user-1", session_id="session-1", artifact_id="artifact-1")

    assert job.state == "completed"
    assert job.findings == {"analysis": "deterministic_csv_profile", "row_count": 1, "findings_stored_in_blob": True}
    assert job.findings_blob_name in derived.items
    assert b'"covered_row_ranges"' in derived.items[job.findings_blob_name].content


@pytest.mark.asyncio
async def test_analysis_records_failed_when_oversized_findings_cannot_be_stored() -> None:
    derived = FailingAnalysisFindingsStorage()
    processing = ArtifactProcessingService(
        StubArtifactService("portfolio.csv", "text/csv", b"symbol\nMSFT\n"), InMemoryManifestRepository(), derived,
        CsvArtifactProcessor(max_rows=10, chunk_rows=1),
    )
    service = ArtifactAnalysisService(processing, InMemoryAnalysisJobRepository(), derived, findings_inline_max_bytes=1)

    job = await service.analyze_entire_file(user_id="user-1", session_id="session-1", artifact_id="artifact-1")

    assert job.state == "failed"
    assert job.error_detail == "Unable to store analysis findings: analysis findings storage unavailable"