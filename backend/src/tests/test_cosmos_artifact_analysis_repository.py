import pytest
from datetime import UTC, datetime, timedelta

from agent_86.domain.models.artifact_analysis import ArtifactAnalysisChunkResult, ArtifactAnalysisJob, ArtifactProcessingManifest
from agent_86.repositories.cosmos_artifact_analysis_repository import CosmosArtifactAnalysisJobRepository, CosmosArtifactProcessingRepository


class FakeContainer:
    def __init__(self) -> None:
        self.items: list[dict] = []

    async def upsert_item(self, item: dict) -> dict:
        self.items = [existing for existing in self.items if existing["id"] != item["id"]] + [item]
        return item

    async def create_item(self, item: dict) -> dict:
        if any(existing["id"] == item["id"] for existing in self.items):
            from azure.cosmos.exceptions import CosmosResourceExistsError

            raise CosmosResourceExistsError(message="conflict", response=None)
        stored = {**item, "_etag": "1"}
        self.items.append(stored)
        return stored

    async def replace_item(self, *, item: str, body: dict, etag: str, match_condition) -> dict:
        for index, existing in enumerate(self.items):
            if existing["id"] == item:
                assert etag == existing["_etag"]
                stored = {**body, "_etag": str(int(etag) + 1)}
                self.items[index] = stored
                return stored
        raise AssertionError("item not found")

    async def query_items(self, *, query: str, parameters: list[dict], partition_key: str):
        values = {item["name"]: item["value"] for item in parameters}
        for item in self.items:
            if item["session_id"] != partition_key:
                continue
            if all(item.get(name[1:]) == value for name, value in values.items()):
                yield item


@pytest.mark.asyncio
async def test_processing_manifest_is_session_and_user_scoped() -> None:
    repository = CosmosArtifactProcessingRepository(FakeContainer())
    manifest = ArtifactProcessingManifest(
        id="manifest-1", session_id="session-1", user_id="user-1", artifact_id="artifact-1",
        source_sha256="a" * 64, state="ready", headers=["symbol"], total_rows=2, chunk_count=1,
    )

    stored = await repository.upsert_manifest(manifest)

    assert stored.created_at is not None
    assert stored.updated_at is not None
    assert await repository.get_manifest("user-1", "session-1", "artifact-1", "a" * 64) == stored
    assert await repository.get_manifest("user-2", "session-1", "artifact-1", "a" * 64) is None
    assert await repository.get_manifest("user-1", "session-2", "artifact-1", "a" * 64) is None


@pytest.mark.asyncio
async def test_analysis_chunk_results_are_session_and_user_scoped() -> None:
    repository = CosmosArtifactAnalysisJobRepository(FakeContainer())
    result = ArtifactAnalysisChunkResult(
        id="job-1:chunk:0", job_id="job-1", session_id="session-1", user_id="user-1", artifact_id="artifact-1",
        chunk_index=0, start_row=1, end_row=2, state="completed", findings={"row_count": 2},
    )

    stored = await repository.upsert_chunk_result(result)

    assert stored.created_at is not None
    assert await repository.list_chunk_results("user-1", "session-1", "job-1") == [stored]
    assert await repository.list_chunk_results("user-2", "session-1", "job-1") == []
    assert await repository.list_chunk_results("user-1", "session-2", "job-1") == []


@pytest.mark.asyncio
async def test_analysis_job_claim_uses_create_then_conditional_replace() -> None:
    repository = CosmosArtifactAnalysisJobRepository(FakeContainer())
    job = ArtifactAnalysisJob(
        id="job-1", session_id="session-1", user_id="user-1", artifact_id="artifact-1",
        source_sha256="a" * 64, analysis_type="csv_profile", state="running",
    )

    claimed = await repository.try_claim_job(job)
    duplicate_claim = await repository.try_claim_job(ArtifactAnalysisJob(
        id="job-1", session_id="session-1", user_id="user-1", artifact_id="artifact-1",
        source_sha256="a" * 64, analysis_type="csv_profile", state="running",
    ))
    claimed.state = "completed"
    updated = await repository.upsert_job(claimed)

    assert claimed is not None
    assert claimed.etag == "1"
    assert duplicate_claim is None
    assert updated.state == "completed"
    assert updated.etag == "2"


@pytest.mark.asyncio
async def test_analysis_job_claim_persists_and_reads_its_lease_expiry() -> None:
    repository = CosmosArtifactAnalysisJobRepository(FakeContainer())
    expiry = datetime.now(UTC) + timedelta(minutes=5)

    claimed = await repository.try_claim_job(ArtifactAnalysisJob(
        id="job-lease", session_id="session-1", user_id="user-1", artifact_id="artifact-1",
        source_sha256="a" * 64, analysis_type="csv_profile", state="running", claim_expires_at=expiry,
    ))

    assert claimed is not None
    assert claimed.claim_expires_at == expiry
    assert "claim_expires_at" in (await repository._get_container()).items[0]