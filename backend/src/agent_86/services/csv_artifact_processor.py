import csv
import hashlib
import io
import json
from dataclasses import dataclass


class CsvArtifactProcessingError(ValueError):
    """Raised when an artifact cannot satisfy the CSV processing contract."""


@dataclass(frozen=True)
class CsvChunk:
    index: int
    start_row: int
    end_row: int
    jsonl: bytes


@dataclass(frozen=True)
class CsvProcessingResult:
    source_sha256: str
    headers: list[str]
    total_rows: int
    chunks: list[CsvChunk]
    normalized_jsonl: bytes


class CsvArtifactProcessor:
    """Deterministically converts a CSV into auditable, row-ranged JSONL chunks."""

    def __init__(self, *, max_rows: int, chunk_rows: int) -> None:
        if max_rows < 1 or chunk_rows < 1:
            raise ValueError("max_rows and chunk_rows must be positive")
        self._max_rows = max_rows
        self._chunk_rows = chunk_rows

    def process(self, content: bytes) -> CsvProcessingResult:
        source_sha256 = hashlib.sha256(content).hexdigest()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CsvArtifactProcessingError("CSV must be UTF-8 encoded") from exc

        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames or not all(header and header.strip() for header in reader.fieldnames):
            raise CsvArtifactProcessingError("CSV must contain a non-empty header row")

        headers = [header.strip() for header in reader.fieldnames]
        if len(set(headers)) != len(headers):
            raise CsvArtifactProcessingError("CSV header names must be unique")

        normalized_lines: list[bytes] = []
        chunks: list[CsvChunk] = []
        current_chunk: list[bytes] = []
        row_number = 0
        for raw_row in reader:
            if raw_row is None or not any((value or "").strip() for value in raw_row.values()):
                continue
            row_number += 1
            if row_number > self._max_rows:
                raise CsvArtifactProcessingError(f"CSV exceeds the {self._max_rows} row limit")
            row = {header: (raw_row.get(original) or "") for header, original in zip(headers, reader.fieldnames)}
            line = json.dumps(
                {"source_row": row_number, "values": row},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            normalized_lines.append(line)
            current_chunk.append(line)
            if len(current_chunk) == self._chunk_rows:
                chunks.append(self._make_chunk(len(chunks), row_number - len(current_chunk) + 1, row_number, current_chunk))
                current_chunk = []

        if current_chunk:
            chunks.append(self._make_chunk(len(chunks), row_number - len(current_chunk) + 1, row_number, current_chunk))
        return CsvProcessingResult(
            source_sha256=source_sha256,
            headers=headers,
            total_rows=row_number,
            chunks=chunks,
            normalized_jsonl=b"".join(normalized_lines),
        )

    @staticmethod
    def _make_chunk(index: int, start_row: int, end_row: int, lines: list[bytes]) -> CsvChunk:
        return CsvChunk(index=index, start_row=start_row, end_row=end_row, jsonl=b"".join(lines))