import { InteractionStatus } from "@azure/msal-browser";
import { useQuery } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";

import * as messagesApi from "@/api/messages";
import { getActiveAccountOrFirst } from "@/auth/msalConfig";

export const messagesQueryKey = (sessionId: string | null) => ["messages", sessionId] as const;

export function useMessages(sessionId: string | null) {
  const { instance, inProgress } = useMsal();
  const account = getActiveAccountOrFirst();

  return useQuery({
    queryKey: messagesQueryKey(sessionId),
    queryFn: () => messagesApi.listMessages(instance, account, sessionId!),
    enabled: Boolean(account && sessionId && inProgress === InteractionStatus.None),
    retry: false,
  });
}