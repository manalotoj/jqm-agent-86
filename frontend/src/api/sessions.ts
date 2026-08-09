import type { IPublicClientApplication, AccountInfo } from "@azure/msal-browser";
import { apiFetch } from "./client";
import type { Session, CreateSessionRequest, UpdateSessionRequest } from "../types/session";

export async function listSessions(
  instance: IPublicClientApplication,
  account: AccountInfo,
): Promise<Session[]> {
  const response = await apiFetch<unknown>("/sessions", instance, account);

  if (!Array.isArray(response)) {
    throw new Error("Invalid sessions response: expected an array.");
  }

  return response as Session[];
}

export const getSession = (
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string
) => apiFetch<Session>(`/sessions/${sessionId}`, instance, account);

export const createSession = (
  instance: IPublicClientApplication,
  account: AccountInfo,
  body: CreateSessionRequest
) =>
  apiFetch<Session>("/sessions", instance, account, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateSession = (
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
  body: UpdateSessionRequest
) =>
  apiFetch<Session>(`/sessions/${sessionId}`, instance, account, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

export const deleteSession = (
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string
) =>
  apiFetch<void>(`/sessions/${sessionId}`, instance, account, {
    method: "DELETE",
  });