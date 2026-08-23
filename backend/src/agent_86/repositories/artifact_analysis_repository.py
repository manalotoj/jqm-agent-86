from typing import Protocol

from agent_86.domain.models.artifact_analysis import ArtifactAnalysisChunkResult, ArtifactAnalysisJob, ArtifactProcessingManifest


class ArtifactProcessingRepository(Protocol):
    async def get_manifest(
        self, user_id: str, session_id: str, artifact_id: str, source_sha256: str
    ) -> ArtifactProcessingManifest | None: ...

    async def upsert_manifest(self, manifest: ArtifactProcessingManifest) -> ArtifactProcessingManifest: ...


class ArtifactAnalysisJobRepository(Protocol):
    async def get_job(self, user_id: str, session_id: str, job_id: str) -> ArtifactAnalysisJob | None: ...

    async def get_job_by_idempotency_key(
        self, user_id: str, session_id: str, artifact_id: str, source_sha256: str, analysis_type: str
    ) -> ArtifactAnalysisJob | None: ...

    async def upsert_job(self, job: ArtifactAnalysisJob) -> ArtifactAnalysisJob: ...

    async def try_claim_job(self, job: ArtifactAnalysisJob) -> ArtifactAnalysisJob | None: ...

    async def list_chunk_results(self, user_id: str, session_id: str, job_id: str) -> list[ArtifactAnalysisChunkResult]: ...

    async def upsert_chunk_result(self, result: ArtifactAnalysisChunkResult) -> ArtifactAnalysisChunkResult: ...