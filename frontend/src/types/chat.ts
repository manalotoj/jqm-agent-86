import type { Message } from "@/types/message";

export interface ChatRequest {
  content: string;
  metadata?: Record<string, unknown>;
  tools?: string[];
}

export interface ChatResponse {
  message: Message;
}

export interface ChatStreamEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface ChatStreamCallbacks {
  onEvent?: (event: ChatStreamEvent) => void;
  onStart?: (event: ChatStreamEvent) => void;
  onDelta?: (text: string, event: ChatStreamEvent) => void;
  onToolCall?: (event: ChatStreamEvent) => void;
  onToolResult?: (event: ChatStreamEvent) => void;
  onComplete?: (event: ChatStreamEvent) => void;
  onErrorEvent?: (event: ChatStreamEvent) => void;
  onDone?: (event: ChatStreamEvent) => void;
}