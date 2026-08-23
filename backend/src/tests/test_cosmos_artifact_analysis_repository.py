import pytest

from agent_86.domain.models.artifact_analysis import ArtifactAnalysisChunkResult, ArtifactProcessingManifest
from agent_86.repositories.cosmos_artifact_analysis_repository import CosmosArtifactAnalysisJobRepository, CosmosArtifactProcessingRepository


class FakeContainer:
    def __init__(self) -> None:
        self.items: list[dict] = []

    async def upsert_item(self, item: dict) -> dict:
        self.items = [existing for existing in self.items if existing["id"] != item["id"]] + [item]
        return item

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