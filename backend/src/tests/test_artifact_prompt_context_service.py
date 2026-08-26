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


# ---------------------------------------------------------------------------
# Image artifact tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_message_for_artifact_ids_detects_png_by_content_type() -> None:
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    service = ArtifactPromptContextService(
        SimpleNamespace(
            get_artifact_content=AsyncMock(
                return_value=SimpleNamespace(
                    artifact=_artifact(artifact_id="img1", filename="portfolio.png", content_type="image/png"),
                    download=BlobDownload(content=png_bytes, content_type="image/png"),
                )
            )
        )
    )

    result = await service.build_message_for_artifact_ids(
        user_id="user-1", session_id="session-1", artifact_ids=["img1"],
    )

    assert result.requires_vision is True
    assert len(result.image_content_blocks) == 1
    block = result.image_content_blocks[0]
    assert block["type"] == "input_image"
    assert block["image_url"].startswith("data:image/png;base64,")
    assert result.artifact_details[0]["strategy"] == "image_inline"
    assert result.artifact_details[0]["is_unreadable"] is False
    assert result.has_unreadable_artifacts is False
    assert result.context_message is not None
    assert "portfolio.png" in result.context_message.content
    assert "Image attached inline" in result.context_message.content
    assert result.context_message.metadata.get("requires_vision") is True


@pytest.mark.asyncio
async def test_build_message_for_artifact_ids_detects_jpeg_by_extension() -> None:
    jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 20
    service = ArtifactPromptContextService(
        SimpleNamespace(
            get_artifact_content=AsyncMock(
                return_value=SimpleNamespace(
                    artifact=_artifact(artifact_id="img2", filename="statement.jpg", content_type="application/octet-stream"),
                    download=BlobDownload(content=jpeg_bytes, content_type="application/octet-stream"),
                )
            )
        )
    )

    result = await service.build_message_for_artifact_ids(
        user_id="user-1", session_id="session-1", artifact_ids=["img2"],
    )

    assert result.requires_vision is True
    assert len(result.image_content_blocks) == 1
    block = result.image_content_blocks[0]
    assert block["type"] == "input_image"
    assert "image/jpeg" in block["image_url"]
    assert result.artifact_details[0]["strategy"] == "image_inline"


@pytest.mark.asyncio
async def test_build_message_for_artifact_ids_rejects_oversized_image() -> None:
    large_bytes = b"\x89PNG" + b"\x00" * (6 * 1024 * 1024)
    service = ArtifactPromptContextService(
        SimpleNamespace(
            get_artifact_content=AsyncMock(
                return_value=SimpleNamespace(
                    artifact=_artifact(artifact_id="img3", filename="huge.png", content_type="image/png"),
                    download=BlobDownload(content=large_bytes, content_type="image/png"),
                )
            )
        ),
        image_max_bytes=5 * 1024 * 1024,
    )

    result = await service.build_message_for_artifact_ids(
        user_id="user-1", session_id="session-1", artifact_ids=["img3"],
    )

    assert result.requires_vision is False
    assert result.image_content_blocks == []
    assert result.has_unreadable_artifacts is True
    assert result.artifact_details[0]["strategy"] == "image_too_large"
    assert result.artifact_details[0]["is_unreadable"] is True
    assert result.context_message is not None
    assert "Image too large" in result.context_message.content


@pytest.mark.asyncio
async def test_build_message_for_artifact_ids_handles_mixed_text_and_image() -> None:
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
    mock_service = SimpleNamespace(
        get_artifact_content=AsyncMock(
            side_effect=[
                SimpleNamespace(
                    artifact=_artifact(artifact_id="t1", filename="notes.txt", content_type="text/plain"),
                    download=BlobDownload(content=b"important note", content_type="text/plain"),
                ),
                SimpleNamespace(
                    artifact=_artifact(artifact_id="img4", filename="chart.png", content_type="image/png"),
                    download=BlobDownload(content=png_bytes, content_type="image/png"),
                ),
            ]
        )
    )
    service = ArtifactPromptContextService(mock_service)

    result = await service.build_message_for_artifact_ids(
        user_id="user-1", session_id="session-1", artifact_ids=["t1", "img4"],
    )

    assert result.requires_vision is True
    assert len(result.image_content_blocks) == 1
    assert result.has_partial_artifacts is False
    assert result.has_unreadable_artifacts is False
    assert len(result.artifact_details) == 2
    text_detail = next(d for d in result.artifact_details if d["id"] == "t1")
    image_detail = next(d for d in result.artifact_details if d["id"] == "img4")
    assert text_detail["strategy"] == "full"
    assert image_detail["strategy"] == "image_inline"
    assert result.context_message is not None
    assert "important note" in result.context_message.content
    assert "chart.png" in result.context_message.content


@pytest.mark.asyncio
async def test_build_message_for_artifact_ids_base64_encodes_image_correctly() -> None:
    import base64 as _base64

    raw_bytes = b"\x89PNG\r\n\x1a\nHELLO"
    service = ArtifactPromptContextService(
        SimpleNamespace(
            get_artifact_content=AsyncMock(
                return_value=SimpleNamespace(
                    artifact=_artifact(artifact_id="img5", filename="test.png", content_type="image/png"),
                    download=BlobDownload(content=raw_bytes, content_type="image/png"),
                )
            )
        )
    )

    result = await service.build_message_for_artifact_ids(
        user_id="user-1", session_id="session-1", artifact_ids=["img5"],
    )

    block = result.image_content_blocks[0]
    prefix = "data:image/png;base64,"
    assert block["image_url"].startswith(prefix)
    encoded_part = block["image_url"][len(prefix):]
    assert _base64.b64decode(encoded_part) == raw_bytes