import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";

import * as artifactsApi from "@/api/artifacts";
import type { UploadArtifactRequest } from "@/types/artifact";

export const artifactsQueryKey = (sessionId: string | null) => ["artifacts", sessionId] as const;

export function useArtifacts(sessionId: string | null) {
  const { instance, accounts } = useMsal();
  const account = accounts[0];

  return useQuery({
    queryKey: artifactsQueryKey(sessionId),
    queryFn: () => artifactsApi.listArtifacts(instance, account, sessionId!),
    enabled: Boolean(account && sessionId),
  });
}

export function useUploadArtifact(sessionId: string | null) {
  const { instance, accounts } = useMsal();
  const account = accounts[0];
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: UploadArtifactRequest) =>
      artifactsApi.uploadArtifact(instance, account, sessionId!, request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: artifactsQueryKey(sessionId) });
    },
  });
}