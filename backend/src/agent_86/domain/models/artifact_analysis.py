from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


ProcessingState = Literal["queued", "processing", "ready", "unsupported", "failed"]
AnalysisState = Literal["requested", "running", "completed", "partial", "failed"]


@dataclass
class ArtifactProcessingManifest:
    id: str
    session_id: str
    user_id: str
    artifact_id: str
    source_sha256: str
    state: ProcessingState
    headers: list[str] = field(default_factory=list)
    total_rows: int = 0
    chunk_count: int = 0
    chunk_row_ranges: list[tuple[int, int]] = field(default_factory=list)
    normalized_blob_name: str | None = None
    chunks_blob_name: str | None = None
    error_detail: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ArtifactAnalysisJob:
    id: str
    session_id: str
    user_id: str
    artifact_id: str
    source_sha256: str
    analysis_type: str
    state: AnalysisState
    expected_rows: int = 0
    successful_rows: int = 0
    failed_rows: int = 0
    expected_chunks: int = 0
    successful_chunks: int = 0
    failed_chunks: int = 0
    findings: dict[str, Any] = field(default_factory=dict)
    findings_blob_name: str | None = None
    error_detail: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    claim_expires_at: datetime | None = None
    etag: str | None = None


@dataclass
class ArtifactAnalysisChunkResult:
    id: str
    job_id: str
    session_id: str
    user_id: str
    artifact_id: str
    chunk_index: int
    start_row: int
    end_row: int
    state: Literal["completed", "failed"]
    findings: dict[str, Any] = field(default_factory=dict)
    error_detail: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None