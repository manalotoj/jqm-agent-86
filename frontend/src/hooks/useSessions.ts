import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";
import * as sessionsApi from "../api/sessions";
import type { CreateSessionRequest, UpdateSessionRequest } from "../types/session";

const SESSIONS_KEY = ["sessions"];

export function useSessions() {
  const { instance, accounts } = useMsal();
  const account = accounts[0];

  return useQuery({
    queryKey: SESSIONS_KEY,
    queryFn: () => sessionsApi.listSessions(instance, account),
    enabled: !!account,
  });
}

export function useCreateSession() {
  const { instance, accounts } = useMsal();
  const account = accounts[0];
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
  const { instance, accounts } = useMsal();
  const account = accounts[0];
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
  const { instance, accounts } = useMsal();
  const account = accounts[0];
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sessionId: string) => sessionsApi.deleteSession(instance, account, sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
    },
  });
}