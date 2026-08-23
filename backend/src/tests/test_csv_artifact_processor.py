import hashlib
import json

import pytest

from agent_86.services.csv_artifact_processor import CsvArtifactProcessingError, CsvArtifactProcessor


def test_csv_processing_assigns_every_non_empty_row_exactly_once() -> None:
    content = b"symbol,quantity\nMSFT,10\n\nAAPL,20\nNVDA,30\nTSLA,40\n"

    result = CsvArtifactProcessor(max_rows=10, chunk_rows=2).process(content)

    assert result.source_sha256 == hashlib.sha256(content).hexdigest()
    assert result.headers == ["symbol", "quantity"]
    assert result.total_rows == 4
    assert [(chunk.start_row, chunk.end_row) for chunk in result.chunks] == [(1, 2), (3, 4)]
    rows = [json.loads(line)["source_row"] for chunk in result.chunks for line in chunk.jsonl.splitlines()]
    assert rows == [1, 2, 3, 4]
    assert [json.loads(line)["source_row"] for line in result.normalized_jsonl.splitlines()] == rows


def test_csv_processing_covers_first_middle_and_last_row_across_chunks() -> None:
    content = b"id\n1\n2\n3\n4\n5\n"

    result = CsvArtifactProcessor(max_rows=10, chunk_rows=2).process(content)

    assert [(chunk.start_row, chunk.end_row) for chunk in result.chunks] == [(1, 2), (3, 4), (5, 5)]
    assert [json.loads(chunk.jsonl.splitlines()[0])["source_row"] for chunk in result.chunks] == [1, 3, 5]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "header"),
        (b"id,id\n1,2\n", "unique"),
        (b"id\n1\n2\n", "exceeds"),
    ],
)
def test_csv_processing_rejects_invalid_or_over_limit_input(content: bytes, message: str) -> None:
    with pytest.raises(CsvArtifactProcessingError, match=message):
        CsvArtifactProcessor(max_rows=1, chunk_rows=1).process(content)