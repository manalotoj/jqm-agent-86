import type { AccountInfo, IPublicClientApplication } from "@azure/msal-browser";

import { API_BASE_URL, ApiError } from "@/api/client";
import { getApiToken } from "@/auth/getApiToken";
import type { ChatRequest, ChatStreamCallbacks, ChatStreamEvent } from "@/types/chat";
import { createInteractionId, trackWorkflowEvent, trackWorkflowException } from "@/telemetry";

function createEventDispatcher(callbacks: ChatStreamCallbacks) {
  return (event: ChatStreamEvent) => {
    callbacks.onEvent?.(event);

    switch (event.event) {
      case "start":
        callbacks.onStart?.(event);
        break;
      case "delta": {
        const text = typeof event.data.text === "string" ? event.data.text : "";
        callbacks.onDelta?.(text, event);
        break;
      }
      case "tool_call":
        callbacks.onToolCall?.(event);
        break;
      case "tool_result":
        callbacks.onToolResult?.(event);
        break;
      case "complete":
        callbacks.onComplete?.(event);
        break;
      case "error":
        callbacks.onErrorEvent?.(event);
        break;
      case "done":
        callbacks.onDone?.(event);
        break;
      default:
        break;
    }
  };
}

function parseSseChunk(
  chunk: string,
  dispatch: (event: ChatStreamEvent) => void,
) {
  const rawEvents = chunk.split("\n\n");

  for (const rawEvent of rawEvents) {
    const trimmed = rawEvent.trim();

    if (!trimmed) {
      continue;
    }

    const lines = trimmed.split("\n");
    let eventName = "message";
    const dataLines: string[] = [];

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventName = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        dataLines.push(line.slice(6));
      }
    }

    let data: Record<string, unknown> = {};
    const payload = dataLines.join("\n").trim();

    if (payload) {
      data = JSON.parse(payload) as Record<string, unknown>;
    }

    dispatch({ event: eventName, data });
  }
}

export async function streamChat(
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
  request: ChatRequest,
  callbacks: ChatStreamCallbacks = {},
) {
  const interactionId = createInteractionId();
  trackWorkflowEvent("chat.stream.started", interactionId);
  const token = await getApiToken(instance, account);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${token}`,
      "x-agent86-interaction-id": interactionId,
    },
    body: JSON.stringify({
      content: request.content,
      metadata: request.metadata ?? {},
      tools: request.tools ?? [],
    }),
    });
  } catch (error) {
    trackWorkflowException(error, interactionId);
    throw error;
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    const error = new ApiError(response.status, body || response.statusText);
    trackWorkflowException(error, interactionId);
    throw error;
  }

  if (!response.body) {
    throw new Error("Streaming response body was not available.");
  }

  const dispatch = createEventDispatcher(callbacks);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const boundary = buffer.lastIndexOf("\n\n");

      if (boundary === -1) {
        continue;
      }

      const completeChunk = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      parseSseChunk(completeChunk, dispatch);
    }

    const finalChunk = buffer + decoder.decode();

    if (finalChunk.trim()) {
      parseSseChunk(finalChunk, dispatch);
    }
  } finally {
    reader.releaseLock();
  }
  trackWorkflowEvent("chat.stream.completed", interactionId);
}