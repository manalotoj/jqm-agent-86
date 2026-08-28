import type { AccountInfo, IPublicClientApplication } from "@azure/msal-browser";

import { apiFetch, API_BASE_URL } from "@/api/client";
import { getApiToken } from "@/auth/getApiToken";
import type { SessionSummary } from "@/types/sessionSummary";

function hasStatusCode(error: unknown, status: number): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    typeof error.status === "number" &&
    error.status === status
  );
}

function isNetworkFetchFailure(error: unknown): boolean {
  return error instanceof TypeError && error.message === "Failed to fetch";
}

export async function getSessionSummary(
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
): Promise<SessionSummary | null> {
  try {
    return await apiFetch<SessionSummary>(`/sessions/${sessionId}/summary`, instance, account);
  } catch (error) {
    if (hasStatusCode(error, 404) || isNetworkFetchFailure(error)) {
      return null;
    }

    throw error;
  }
}

export function generateSessionSummary(
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
) {
  return apiFetch<SessionSummary>(`/sessions/${sessionId}/summary`, instance, account, {
    method: "POST",
  });
}

export async function generateContextSummary(
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
): Promise<string> {
  const token = await getApiToken(instance, account);

  const response = await fetch(
    `${API_BASE_URL}/sessions/${sessionId}/context-summary`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    },
  );

  if (!response.ok || !response.body) {
    throw new Error(`Context summary request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data:")) {
        try {
          const payload = JSON.parse(line.slice("data:".length).trim()) as Record<string, unknown>;
          if (typeof payload.text === "string") {
            text += payload.text;
          }
        } catch {
          // skip malformed lines
        }
      }
    }
  }

  return text;
}