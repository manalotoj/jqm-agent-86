from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProcessingState = Literal["queued", "processing", "ready", "unsupported", "failed"]
AnalysisState = Literal["requested", "running", "completed", "partial", "failed"]


class ArtifactProcessingManifestResponse(BaseModel):
    id: str
    artifact_id: str
    source_sha256: str
    state: ProcessingState
    headers: list[str] = Field(default_factory=list)
    total_rows: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    chunk_row_ranges: list[tuple[int, int]] = Field(default_factory=list)
    error_detail: str | None = None
    created_at: datetime
    updated_at: datetime
    claim_expires_at: datetime | None = None


class ArtifactAnalysisJobResponse(BaseModel):
    id: str
    artifact_id: str
    source_sha256: str
    analysis_type: str
    state: AnalysisState
    expected_rows: int = Field(ge=0)
    successful_rows: int = Field(ge=0)
    failed_rows: int = Field(ge=0)
    expected_chunks: int = Field(ge=0)
    successful_chunks: int = Field(ge=0)
    failed_chunks: int = Field(ge=0)
    findings: dict[str, Any] = Field(default_factory=dict)
    findings_blob_name: str | None = None
    error_detail: str | None = None
    created_at: datetime
    updated_at: datetime