import { InteractionStatus } from "@azure/msal-browser";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";

import * as sessionSummariesApi from "@/api/sessionSummaries";
import { getActiveAccountOrFirst } from "@/auth/msalConfig";

export const sessionSummaryQueryKey = (sessionId: string | null) =>
  ["session-summary", sessionId] as const;

export function useSessionSummary(sessionId: string | null) {
  const { instance, inProgress } = useMsal();
  const account = getActiveAccountOrFirst();

  return useQuery({
    queryKey: sessionSummaryQueryKey(sessionId),
    queryFn: () => sessionSummariesApi.getSessionSummary(instance, account, sessionId!),
    enabled: Boolean(account && sessionId && inProgress === InteractionStatus.None),
    retry: false,
  });
}

export function useGenerateSessionSummary(sessionId: string | null) {
  const { instance } = useMsal();
  const account = getActiveAccountOrFirst();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => sessionSummariesApi.generateSessionSummary(instance, account, sessionId!),
    onSuccess: (summary) => {
      queryClient.setQueryData(sessionSummaryQueryKey(sessionId), summary);
      queryClient.invalidateQueries({ queryKey: sessionSummaryQueryKey(sessionId) });
    },
  });
}

export function useGenerateContextSummary(sessionId: string | null) {
  const { instance } = useMsal();
  const account = getActiveAccountOrFirst();

  return useMutation({
    mutationFn: () => sessionSummariesApi.generateContextSummary(instance, account, sessionId!),
  });
}