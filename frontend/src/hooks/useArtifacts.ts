import { InteractionStatus } from "@azure/msal-browser";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";

import * as artifactsApi from "@/api/artifacts";
import type { UploadArtifactRequest } from "@/types/artifact";
import { getActiveAccountOrFirst } from "@/auth/msalConfig";

export const artifactsQueryKey = (sessionId: string | null) => ["artifacts", sessionId] as const;
export const artifactAnalysisQueryKey = (sessionId: string | null, jobId: string | null) =>
  ["artifact-analysis", sessionId, jobId] as const;

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

export function useAnalyzeArtifact(sessionId: string | null) {
  const { instance } = useMsal();
  const account = getActiveAccountOrFirst();

  return useMutation({
    mutationFn: (artifactId: string) => artifactsApi.analyzeArtifact(instance, account, sessionId!, artifactId),
  });
}

export function useArtifactAnalysis(
  sessionId: string | null,
  artifactId: string,
  jobId: string | null,
) {
  const { instance, inProgress } = useMsal();
  const account = getActiveAccountOrFirst();

  return useQuery({
    queryKey: artifactAnalysisQueryKey(sessionId, jobId),
    queryFn: () => artifactsApi.getArtifactAnalysis(instance, account, sessionId!, artifactId, jobId!),
    enabled: Boolean(account && sessionId && jobId && inProgress === InteractionStatus.None),
    retry: false,
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "requested" || state === "running" ? 2000 : false;
    },
  });
}