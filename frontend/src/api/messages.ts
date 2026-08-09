import type { AccountInfo, IPublicClientApplication } from "@azure/msal-browser";

import { apiFetch } from "@/api/client";
import type { Message } from "@/types/message";

export const listMessages = (
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
) => apiFetch<Message[]>(`/sessions/${sessionId}/messages`, instance, account);