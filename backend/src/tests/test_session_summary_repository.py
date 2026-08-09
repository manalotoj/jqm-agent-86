from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_86.domain.models.session_summary import SessionSummary
from agent_86.domain.schemas.session_summary import ActionItem, ArtifactRef
from agent_86.repositories.cosmos_session_summary_repository import CosmosSessionSummaryRepository


@pytest.mark.asyncio
async def test_upsert_summary_reuses_existing_document_id_and_created_at() -> None:
    container = SimpleNamespace()
    repository = CosmosSessionSummaryRepository(container)

    existing_document = {
        "id": "summary:session-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "title": "Old title",
        "date_range_start": datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "date_range_end": datetime(2026, 1, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "one_line_summary": "Old summary",
        "topics": ["old"],
        "key_decisions": [],
        "action_items": [],
        "artifacts_generated": [],
        "open_questions": [],
        "tools_used": [],
        "tags": [],
        "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
    }

    async def query_items(*args, **kwargs):
        yield existing_document

    container.query_items = query_items
    container.upsert_item = AsyncMock(side_effect=lambda document: document)

    summary = SessionSummary(
        id="summary:session-1-new",
        session_id="session-1",
        user_id="user-1",
        title="New title",
        date_range_start=datetime(2026, 1, 1, tzinfo=UTC),
        date_range_end=datetime(2026, 1, 2, tzinfo=UTC),
        one_line_summary="New summary",
        topics=["new"],
        key_decisions=["Do the thing"],
        action_items=[ActionItem(description="Ship", status="open", owner="me")],
        artifacts_generated=[ArtifactRef(name="plan.docx", artifact_type="docx", location="artifact-1")],
        open_questions=["When?"],
        tools_used=["web_search"],
        tags=["important"],
    )

    stored = await repository.upsert_summary(summary)

    container.upsert_item.assert_awaited_once()
    upserted_document = container.upsert_item.await_args.args[0]
    assert upserted_document["id"] == "summary:session-1"
    assert upserted_document["created_at"] == existing_document["created_at"]
    assert upserted_document["title"] == "New title"
    assert stored.id == "summary:session-1"
    assert stored.created_at == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_repository_resolves_awaitable_container_once() -> None:
    existing_document = {
        "id": "summary:session-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "title": "Old title",
        "date_range_start": datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "date_range_end": datetime(2026, 1, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "one_line_summary": "Old summary",
        "topics": [],
        "key_decisions": [],
        "action_items": [],
        "artifacts_generated": [],
        "open_questions": [],
        "tools_used": [],
        "tags": [],
        "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
    }

    async def query_items(*args, **kwargs):
        yield existing_document

    container = SimpleNamespace(query_items=query_items, upsert_item=AsyncMock(side_effect=lambda document: document))
    container_factory = AsyncMock(return_value=container)
    repository = CosmosSessionSummaryRepository(container_factory())

    first = await repository.get_summary("user-1", "session-1")
    second = await repository.get_summary("user-1", "session-1")

    assert first is not None
    assert second is not None
    container_factory.assert_awaited_once()
