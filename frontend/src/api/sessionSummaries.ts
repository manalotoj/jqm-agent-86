import type { AccountInfo, IPublicClientApplication } from "@azure/msal-browser";

import { apiFetch } from "@/api/client";
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