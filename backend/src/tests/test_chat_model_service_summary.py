from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_86.services.chat_model_service import ChatModelService


def _summary_service(output_text: str) -> ChatModelService:
    service = ChatModelService.__new__(ChatModelService)
    service._client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(output_text=output_text)))
    )
    return service


@pytest.mark.asyncio
async def test_generate_structured_summary_parses_json_markdown_block() -> None:
    service = _summary_service(
        """```json
{
  "session_id": "session-1",
  "title": "Planning sync",
  "date_range_start": "2026-01-01T00:00:00Z",
  "date_range_end": "2026-01-01T00:30:00Z",
  "one_line_summary": "The team discussed planning.",
  "topics": ["planning"],
  "key_decisions": [],
  "action_items": [],
  "artifacts_generated": [],
  "open_questions": [],
  "tools_used": [],
  "tags": [],
  "continuation_context": "You were planning a migration. The next step is to draft the runbook."
}
```"""
    )

    summary = await service.generate_structured_summary(
        model="gpt-4.1-mini", system_prompt="summarize", context_payload={"session_id": "session-1"}
    )

    assert summary.session_id == "session-1"
    assert summary.title == "Planning sync"
    assert summary.continuation_context == "You were planning a migration. The next step is to draft the runbook."


@pytest.mark.asyncio
async def test_generate_structured_summary_backfills_missing_required_fields_from_context() -> None:
    service = _summary_service(
        """{
  "session_id": "session-1",
  "title": "Planning sync",
  "topics": ["planning", "migration"],
  "key_decisions": [],
  "action_items": [],
  "artifact_refs": [],
  "open_questions": [],
  "tools_used": [],
  "tags": []
}"""
    )

    summary = await service.generate_structured_summary(
        model="gpt-4.1-mini",
        system_prompt="summarize",
        context_payload={
            "session_id": "session-1",
            "date_range_start": "2026-01-01T00:00:00Z",
            "date_range_end": "2026-01-01T00:30:00Z",
        },
    )

    assert summary.session_id == "session-1"
    assert summary.date_range_start.isoformat().replace("+00:00", "Z") == "2026-01-01T00:00:00Z"
    assert summary.date_range_end.isoformat().replace("+00:00", "Z") == "2026-01-01T00:30:00Z"
    assert summary.one_line_summary == "Planning sync: planning, migration."
    assert summary.artifacts_generated == []


@pytest.mark.asyncio
async def test_generate_structured_summary_resolves_persisted_artifact_ids() -> None:
    service = _summary_service(
        """{
  "session_id": "session-1",
  "title": "Portfolio review",
  "date_range_start": "2026-01-01T00:00:00Z",
  "date_range_end": "2026-01-01T00:30:00Z",
  "one_line_summary": "The portfolio was reviewed.",
  "artifacts_generated": ["artifact-1", "artifact-2"]
}"""
    )

    summary = await service.generate_structured_summary(
        model="gpt-4.1-mini",
        system_prompt="summarize",
        context_payload={
            "session_id": "session-1",
            "persisted_artifacts": [
                {
                    "id": "artifact-1",
                    "filename": "portfolio.docx",
                    "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                },
                {"id": "artifact-2", "filename": "allocation.json", "content_type": "application/json"},
            ],
        },
    )

    assert [artifact.model_dump() for artifact in summary.artifacts_generated] == [
        {"name": "portfolio.docx", "artifact_type": "docx", "location": "artifact-1"},
        {"name": "allocation.json", "artifact_type": "code", "location": "artifact-2"},
    ]


@pytest.mark.asyncio
async def test_generate_structured_summary_drops_unknown_bare_artifact_ids_and_preserves_objects() -> None:
    service = _summary_service(
        """{
  "session_id": "session-1",
  "title": "Portfolio review",
  "date_range_start": "2026-01-01T00:00:00Z",
  "date_range_end": "2026-01-01T00:30:00Z",
  "one_line_summary": "The portfolio was reviewed.",
  "artifacts_generated": ["unknown-artifact", {"name": "notes.md", "artifact_type": "code", "location": "message-reference"}]
}"""
    )

    summary = await service.generate_structured_summary(
        model="gpt-4.1-mini",
        system_prompt="summarize",
        context_payload={"session_id": "session-1", "persisted_artifacts": []},
    )

    assert [artifact.model_dump() for artifact in summary.artifacts_generated] == [
        {"name": "notes.md", "artifact_type": "code", "location": "message-reference"}
    ]


@pytest.mark.asyncio
async def test_generate_structured_summary_defaults_continuation_context_to_empty_when_absent() -> None:
    service = _summary_service(
        """{
  "session_id": "session-1",
  "title": "Quick chat",
  "date_range_start": "2026-01-01T00:00:00Z",
  "date_range_end": "2026-01-01T00:05:00Z",
  "one_line_summary": "A brief exchange with no continuation context provided."
}"""
    )

    summary = await service.generate_structured_summary(
        model="gpt-4.1-mini",
        system_prompt="summarize",
        context_payload={
            "session_id": "session-1",
            "date_range_start": "2026-01-01T00:00:00Z",
            "date_range_end": "2026-01-01T00:05:00Z",
        },
    )

    assert summary.continuation_context == ""


@pytest.mark.asyncio
async def test_generate_structured_summary_preserves_continuation_context_when_provided() -> None:
    expected_context = (
        "You were working on a database migration plan. "
        "You decided to use a phased rollout approach. "
        "The runbook draft (runbook.md) is attached and covers phases 1 and 2. "
        "Phase 3 cutover timing is still open. "
        "The next step is to confirm the maintenance window with the ops team."
    )
    service = _summary_service(
        f"""{{
  "session_id": "session-2",
  "title": "Database migration planning",
  "date_range_start": "2026-03-01T10:00:00Z",
  "date_range_end": "2026-03-01T11:00:00Z",
  "one_line_summary": "Planned a phased database migration with an open cutover question.",
  "topics": ["migration", "database"],
  "key_decisions": ["Use phased rollout"],
  "action_items": [],
  "artifacts_generated": [],
  "open_questions": ["When is the maintenance window?"],
  "tools_used": [],
  "tags": ["migration"],
  "continuation_context": "{expected_context}"
}}"""
    )

    summary = await service.generate_structured_summary(
        model="gpt-4.1-mini",
        system_prompt="summarize",
        context_payload={
            "session_id": "session-2",
            "date_range_start": "2026-03-01T10:00:00Z",
            "date_range_end": "2026-03-01T11:00:00Z",
        },
    )

    assert summary.continuation_context == expected_context