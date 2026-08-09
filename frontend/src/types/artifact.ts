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