import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { InteractionStatus } from "@azure/msal-browser";
import { useMsal } from "@azure/msal-react";
import * as sessionsApi from "../api/sessions";
import type { CreateSessionRequest, UpdateSessionRequest } from "../types/session";
import { getActiveAccountOrFirst } from "@/auth/msalConfig";

const SESSIONS_KEY = ["sessions"];

export function useSessions() {
  const { instance, inProgress } = useMsal();
  const account = getActiveAccountOrFirst();

  return useQuery({
    queryKey: SESSIONS_KEY,
    queryFn: () => sessionsApi.listSessions(instance, account),
    enabled: Boolean(account && inProgress === InteractionStatus.None),
  });
}

export function useCreateSession() {
  const { instance } = useMsal();
  const account = getActiveAccountOrFirst();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: CreateSessionRequest) =>
      sessionsApi.createSession(instance, account, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
    },
  });
}

export function useUpdateSession() {
  const { instance } = useMsal();
  const account = getActiveAccountOrFirst();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ sessionId, body }: { sessionId: string; body: UpdateSessionRequest }) =>
      sessionsApi.updateSession(instance, account, sessionId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
    },
  });
}

export function useDeleteSession() {
  const { instance } = useMsal();
  const account = getActiveAccountOrFirst();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sessionId: string) => sessionsApi.deleteSession(instance, account, sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
    },
  });
}