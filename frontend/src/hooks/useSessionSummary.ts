import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";

import * as sessionSummariesApi from "@/api/sessionSummaries";

export const sessionSummaryQueryKey = (sessionId: string | null) =>
  ["session-summary", sessionId] as const;

export function useSessionSummary(sessionId: string | null) {
  const { instance, accounts } = useMsal();
  const account = accounts[0];

  return useQuery({
    queryKey: sessionSummaryQueryKey(sessionId),
    queryFn: () => sessionSummariesApi.getSessionSummary(instance, account, sessionId!),
    enabled: Boolean(account && sessionId),
  });
}

export function useGenerateSessionSummary(sessionId: string | null) {
  const { instance, accounts } = useMsal();
  const account = accounts[0];
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => sessionSummariesApi.generateSessionSummary(instance, account, sessionId!),
    onSuccess: (summary) => {
      queryClient.setQueryData(sessionSummaryQueryKey(sessionId), summary);
      queryClient.invalidateQueries({ queryKey: sessionSummaryQueryKey(sessionId) });
    },
  });
}