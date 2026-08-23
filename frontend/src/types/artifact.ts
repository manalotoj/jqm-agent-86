export interface Artifact {
  id: string;
  session_id: string;
  user_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface UploadArtifactRequest {
  file: File;
  metadata?: Record<string, unknown>;
}

export interface DownloadArtifactResult {
  blob: Blob;
  filename: string;
  contentType: string;
}

export type ArtifactAnalysisState = "requested" | "running" | "completed" | "partial" | "failed";

export interface ArtifactAnalysisJob {
  id: string;
  artifact_id: string;
  source_sha256: string;
  analysis_type: string;
  state: ArtifactAnalysisState;
  expected_rows: number;
  successful_rows: number;
  failed_rows: number;
  expected_chunks: number;
  successful_chunks: number;
  failed_chunks: number;
  findings: Record<string, unknown>;
  findings_blob_name: string | null;
  error_detail: string | null;
  created_at: string;
  updated_at: string;
  claim_expires_at: string | null;
}