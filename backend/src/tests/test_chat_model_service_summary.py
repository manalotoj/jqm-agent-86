from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_86.services.chat_model_service import ChatModelService


@pytest.mark.asyncio
async def test_generate_structured_summary_parses_json_markdown_block() -> None:
    service = ChatModelService.__new__(ChatModelService)
    service._client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    output_text="""```json
{
  \"session_id\": \"session-1\",
  \"title\": \"Planning sync\",
  \"date_range_start\": \"2026-01-01T00:00:00Z\",
  \"date_range_end\": \"2026-01-01T00:30:00Z\",
  \"one_line_summary\": \"The team discussed planning.\",
  \"topics\": [\"planning\"],
  \"key_decisions\": [],
  \"action_items\": [],
  \"artifacts_generated\": [],
  \"open_questions\": [],
  \"tools_used\": [],
  \"tags\": []
}
```"""
                )
            )
        )
    )

    summary = await service.generate_structured_summary(
        model="gpt-4.1-mini",
        system_prompt="summarize",
        context_payload={"session_id": "session-1"},
    )

    assert summary.session_id == "session-1"
    assert summary.title == "Planning sync"


@pytest.mark.asyncio
async def test_generate_structured_summary_backfills_missing_required_fields_from_context() -> None:
    service = ChatModelService.__new__(ChatModelService)
    service._client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    output_text="""{
  \"session_id\": \"session-1\",
  \"title\": \"Planning sync\",
  \"topics\": [\"planning\", \"migration\"],
  \"key_decisions\": [],
  \"action_items\": [],
  \"artifact_refs\": [],
  \"open_questions\": [],
  \"tools_used\": [],
  \"tags\": []
}"""
                )
            )
        )
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