export interface Session {
  id: string;
  user_id: string;
  title: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateSessionRequest {
  title?: string | null;
  metadata?: Record<string, unknown>;
}

export interface UpdateSessionRequest {
  title?: string | null;
  metadata?: Record<string, unknown>;
}