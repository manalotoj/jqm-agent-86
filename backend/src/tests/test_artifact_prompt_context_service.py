from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_86.domain.models.artifact import Artifact
from agent_86.services.artifact_prompt_context_service import ArtifactPromptContextService
from agent_86.services.blob_storage_service import BlobDownload


def _artifact(*, artifact_id: str, filename: str, content_type: str) -> Artifact:
    return Artifact(
        id=artifact_id,
        session_id="session-1",
        user_id="user-1",
        filename=filename,
        content_type=content_type,
        size_bytes=0,
        blob_name=f"blob/{artifact_id}",
        metadata={},
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_build_message_for_artifact_ids_includes_full_text_for_small_supported_artifact() -> None:
    service = ArtifactPromptContextService(
        SimpleNamespace(
            get_artifact_content=AsyncMock(
                return_value=SimpleNamespace(
                    artifact=_artifact(artifact_id="a1", filename="notes.txt", content_type="text/plain"),
                    download=BlobDownload(content=b"hello artifact", content_type="text/plain"),
                )
            )
        )
    )

    result = await service.build_message_for_artifact_ids(
        user_id="user-1",
        session_id="session-1",
        artifact_ids=["a1"],
    )

    assert result.context_message is not None
    assert "Full text provided" in result.context_message.content
    assert "hello artifact" in result.context_message.content
    assert result.has_partial_artifacts is False
    assert result.has_unreadable_artifacts is False
    assert result.artifact_details[0]["strategy"] == "full"


@pytest.mark.asyncio
async def test_build_message_for_artifact_ids_uses_head_tail_for_medium_artifact() -> None:
    content = ("A" * 12) + ("M" * 10) + ("Z" * 12)
    service = ArtifactPromptContextService(
        SimpleNamespace(
            get_artifact_content=AsyncMock(
                return_value=SimpleNamespace(
                    artifact=_artifact(artifact_id="a2", filename="medium.md", content_type="text/markdown"),
                    download=BlobDownload(content=content.encode("utf-8"), content_type="text/markdown"),
                )
            )
        ),
        small_file_char_limit=10,
        medium_file_char_limit=40,
        medium_head_char_count=12,
        medium_tail_char_count=12,
    )

    result = await service.build_message_for_artifact_ids(
        user_id="user-1",
        session_id="session-1",
        artifact_ids=["a2"],
    )

    assert result.context_message is not None
    assert "Head and tail excerpt" in result.context_message.content
    assert "OMITTED MIDDLE (10 chars not shown)" in result.context_message.content
    assert "AAAAAAAAAAAA" in result.context_message.content
    assert "ZZZZZZZZZZZZ" in result.context_message.content
    assert result.has_partial_artifacts is True
    assert result.artifact_details[0]["strategy"] == "head_tail"


@pytest.mark.asyncio
async def test_build_message_for_artifact_ids_uses_truncated_excerpt_for_large_artifact() -> None:
    content = "B" * 50
    service = ArtifactPromptContextService(
        SimpleNamespace(
            get_artifact_content=AsyncMock(
                return_value=SimpleNamespace(
                    artifact=_artifact(artifact_id="a3", filename="large.json", content_type="application/json"),
                    download=BlobDownload(content=content.encode("utf-8"), content_type="application/json"),
                )
            )
        ),
        small_file_char_limit=10,
        medium_file_char_limit=20,
        large_excerpt_char_count=15,
    )

    result = await service.build_message_for_artifact_ids(
        user_id="user-1",
        session_id="session-1",
        artifact_ids=["a3"],
    )

    assert result.context_message is not None
    assert "Truncated excerpt" in result.context_message.content
    assert "omitted trailing content: 35 characters" in result.context_message.content
    assert ("B" * 15) in result.context_message.content
    assert result.has_partial_artifacts is True
    assert result.artifact_details[0]["strategy"] == "truncated"


@pytest.mark.asyncio
async def test_build_message_for_artifact_ids_marks_unsupported_artifact_unreadable() -> None:
    service = ArtifactPromptContextService(
        SimpleNamespace(
            get_artifact_content=AsyncMock(
                return_value=SimpleNamespace(
                    artifact=_artifact(artifact_id="a4", filename="diagram.pdf", content_type="application/pdf"),
                    download=BlobDownload(content=b"%PDF", content_type="application/pdf"),
                )
            )
        )
    )

    result = await service.build_message_for_artifact_ids(
        user_id="user-1",
        session_id="session-1",
        artifact_ids=["a4"],
    )

    assert result.context_message is not None
    assert "attached but unreadable in v1" in result.context_message.content
    assert result.has_unreadable_artifacts is True
    assert result.artifact_details[0]["strategy"] == "unreadable"