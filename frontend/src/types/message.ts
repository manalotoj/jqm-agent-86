export type MessageRole = "system" | "user" | "assistant" | "tool";

export interface Message {
  id: string;
  session_id: string;
  user_id: string;
  role: MessageRole;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface CreateMessageRequest {
  role: MessageRole;
  content: string;
  metadata?: Record<string, unknown>;
}