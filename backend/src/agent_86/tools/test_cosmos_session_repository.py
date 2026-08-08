from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from agent_86.domain.schemas.session import UpdateSessionRequest
from agent_86.repositories.cosmos_session_repository import CosmosSessionRepository


@pytest.mark.asyncio
async def test_update_session_uses_upsert_item_with_updated_document() -> None:
    container = AsyncMock()
    repository = CosmosSessionRepository(container)

    existing_document = {
        "id": "session-1",
        "user_id": "user-1",
        "title": "New session 001",
        "metadata": {"origin": "ui"},
        "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
    }
    updated_document = {
        **existing_document,
        "title": "Renamed from prompt",
        "updated_at": datetime(2026, 1, 2, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
    }

    async def query_items(*args, **kwargs):
        yield existing_document

    container.query_items.side_effect = query_items
    container.upsert_item.return_value = updated_document

    session = await repository.update_session(
        user_id="user-1",
        session_id="session-1",
        request=UpdateSessionRequest(title="Renamed from prompt"),
    )

    container.upsert_item.assert_awaited_once()
    upserted_document = container.upsert_item.await_args.args[0]
    assert upserted_document["id"] == "session-1"
    assert upserted_document["user_id"] == "user-1"
    assert upserted_document["title"] == "Renamed from prompt"
    assert upserted_document["metadata"] == {"origin": "ui"}
    assert upserted_document["updated_at"] != existing_document["updated_at"]
    assert session is not None
    assert session.title == "Renamed from prompt"