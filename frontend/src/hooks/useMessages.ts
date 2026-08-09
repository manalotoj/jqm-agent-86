import { useQuery } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";

import * as messagesApi from "@/api/messages";

export const messagesQueryKey = (sessionId: string | null) => ["messages", sessionId] as const;

export function useMessages(sessionId: string | null) {
  const { instance, accounts } = useMsal();
  const account = accounts[0];

  return useQuery({
    queryKey: messagesQueryKey(sessionId),
    queryFn: () => messagesApi.listMessages(instance, account, sessionId!),
    enabled: Boolean(account && sessionId),
  });
}