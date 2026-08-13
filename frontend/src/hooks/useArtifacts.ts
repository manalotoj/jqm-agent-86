import { InteractionStatus } from "@azure/msal-browser";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";

import * as artifactsApi from "@/api/artifacts";
import type { UploadArtifactRequest } from "@/types/artifact";
import { getActiveAccountOrFirst } from "@/auth/msalConfig";

export const artifactsQueryKey = (sessionId: string | null) => ["artifacts", sessionId] as const;

export function useArtifacts(sessionId: string | null) {
  const { instance, inProgress } = useMsal();
  const account = getActiveAccountOrFirst();

  return useQuery({
    queryKey: artifactsQueryKey(sessionId),
    queryFn: () => artifactsApi.listArtifacts(instance, account, sessionId!),
    enabled: Boolean(account && sessionId && inProgress === InteractionStatus.None),
    retry: false,
  });
}

export function useUploadArtifact(sessionId: string | null) {
  const { instance } = useMsal();
  const account = getActiveAccountOrFirst();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: UploadArtifactRequest) =>
      artifactsApi.uploadArtifact(instance, account, sessionId!, request),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: artifactsQueryKey(sessionId) });
    },
  });
}