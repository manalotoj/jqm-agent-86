import { useEffect, useMemo, useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";
import {
  AuthenticatedTemplate,
  UnauthenticatedTemplate,
  useMsal,
} from "@azure/msal-react";
import {
  Bot,
  LoaderCircle,
  LogOut,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Send,
  Sparkles,
  Trash2,
  User,
  WandSparkles,
} from "lucide-react";

import { streamChat } from "@/api/chat";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useMessages, messagesQueryKey } from "@/hooks/useMessages";
import {
  useCreateSession,
  useDeleteSession,
  useSessions,
  useUpdateSession,
} from "@/hooks/useSessions";
import { cn } from "@/lib/utils";
import type { Message } from "@/types/message";
import type { Session } from "@/types/session";

const LOGIN_SCOPES = [import.meta.env.VITE_API_SCOPE].filter(
  (scope): scope is string => Boolean(scope),
);

const DEFAULT_CHAT_MODEL = "gpt-4.1-mini";
const PREMIUM_CHAT_MODEL = "gpt-5.4";

type ComposerModel = typeof DEFAULT_CHAT_MODEL | typeof PREMIUM_CHAT_MODEL;

const MODEL_OPTIONS: Array<{ label: string; value: ComposerModel; description: string }> = [
  {
    label: "Fast",
    value: DEFAULT_CHAT_MODEL,
    description: "gpt-4.1-mini",
  },
  {
    label: "Premium",
    value: PREMIUM_CHAT_MODEL,
    description: "gpt-5.4",
  },
];

function formatSessionTimestamp(value: string | null) {
  if (!value) {
    return "Just now";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Recently updated";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatMessageTimestamp(value: string | null) {
  if (!value) {
    return "Pending";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Pending";
  }

  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function getDisplayTitle(session: Session) {
  return session.title?.trim() || "Untitled session";
}

function getInitials(name?: string | null) {
  if (!name) {
    return "A";
  }

  const parts = name
    .split(" ")
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 2);

  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "A";
}

function getAssistantModel(message: Message | null) {
  const model = message?.metadata?.model;
  return typeof model === "string" ? model : null;
}

function getAssistantTools(message: Message | null) {
  const tools = message?.metadata?.tools;
  return Array.isArray(tools) ? tools.filter((tool): tool is string => typeof tool === "string") : [];
}

function createOptimisticUserMessage(sessionId: string, userId: string, content: string): Message {
  const timestamp = new Date().toISOString();

  return {
    id: `optimistic-user-${crypto.randomUUID()}`,
    session_id: sessionId,
    user_id: userId,
    role: "user",
    content,
    metadata: {},
    created_at: timestamp,
  };
}

function createOptimisticAssistantMessage(
  sessionId: string,
  userId: string,
  model: string,
): Message {
  const timestamp = new Date().toISOString();

  return {
    id: `optimistic-assistant-${crypto.randomUUID()}`,
    session_id: sessionId,
    user_id: userId,
    role: "assistant",
    content: "",
    metadata: {
      source: "foundry",
      model,
      tools: [],
    },
    created_at: timestamp,
  };
}

function SessionSidebarItem({
  session,
  isActive,
  onSelect,
  onRename,
  onDelete,
  isDeleting,
}: {
  session: Session;
  isActive: boolean;
  onSelect: (sessionId: string) => void;
  onRename: (session: Session) => void;
  onDelete: (sessionId: string) => void;
  isDeleting: boolean;
}) {
  return (
    <div
      className={cn(
        "group flex items-center gap-2 rounded-xl border px-3 py-3 transition-colors",
        isActive
          ? "border-sidebar-border bg-sidebar-accent text-sidebar-accent-foreground shadow-xs"
          : "border-transparent text-sidebar-foreground hover:bg-sidebar-accent/60",
      )}
    >
      <button
        type="button"
        onClick={() => onSelect(session.id)}
        className="flex min-w-0 flex-1 items-start gap-3 text-left"
      >
        <div className="mt-0.5 rounded-lg bg-sidebar-primary/10 p-2 text-sidebar-primary">
          <MessageSquare className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{getDisplayTitle(session)}</p>
          <p className="truncate text-xs text-sidebar-foreground/70">
            {formatSessionTimestamp(session.updated_at ?? session.created_at)}
          </p>
        </div>
      </button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-sidebar-foreground/70 hover:text-sidebar-foreground"
          >
            <MoreHorizontal className="size-4" />
            <span className="sr-only">Session actions</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-40">
          <DropdownMenuItem onClick={() => onRename(session)}>
            <Pencil className="size-4" />
            Rename
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => onDelete(session.id)}
            disabled={isDeleting}
            variant="destructive"
          >
            <Trash2 className="size-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const model = getAssistantModel(message);
  const tools = getAssistantTools(message);

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex max-w-[85%] gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
        <div
          className={cn(
            "mt-1 flex size-8 shrink-0 items-center justify-center rounded-full border",
            isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
          )}
        >
          {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
        </div>
        <div
          className={cn(
            "rounded-2xl border px-4 py-3 shadow-xs",
            isUser
              ? "rounded-br-md border-primary bg-primary text-primary-foreground"
              : "rounded-bl-md bg-card",
          )}
        >
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className={cn("font-medium", isUser ? "text-primary-foreground/80" : "text-muted-foreground")}>
              {isUser ? "You" : "Assistant"}
            </span>
            <span className={cn(isUser ? "text-primary-foreground/70" : "text-muted-foreground")}>
              {formatMessageTimestamp(message.created_at)}
            </span>
            {!isUser && model ? (
              <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                {model}
              </span>
            ) : null}
          </div>
          <p className={cn("mt-2 whitespace-pre-wrap text-sm leading-6", isUser && "text-primary-foreground")}>
            {message.content || "…"}
          </p>
          {!isUser && tools.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {tools.map((tool) => (
                <span
                  key={tool}
                  className="rounded-full border bg-muted/60 px-2 py-1 text-[11px] text-muted-foreground"
                >
                  Tool: {tool}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function EmptyConversationState() {
  return (
    <div className="flex h-full flex-col items-center justify-center rounded-2xl border border-dashed bg-muted/20 px-6 py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Sparkles className="size-5" />
      </div>
      <h3 className="mt-4 text-lg font-semibold">Start the conversation</h3>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
        Send the first message in this session to create persisted chat history, stream assistant
        responses, and exercise the backend session/message flow end to end.
      </p>
    </div>
  );
}

function AuthenticatedApp() {
  const { instance, accounts } = useMsal();
  const activeAccount = accounts[0];
  const activeUserId = String(activeAccount?.idTokenClaims?.oid ?? activeAccount?.localAccountId ?? "current-user");
  const queryClient = useQueryClient();

  const { data: sessions = [], isLoading, error } = useSessions();
  const createSession = useCreateSession();
  const updateSession = useUpdateSession();
  const deleteSession = useDeleteSession();

  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [newSessionTitle, setNewSessionTitle] = useState("");
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [draftMessage, setDraftMessage] = useState("");
  const [selectedModel, setSelectedModel] = useState<ComposerModel>(DEFAULT_CHAT_MODEL);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [streamingStatus, setStreamingStatus] = useState<string | null>(null);
  const [lastStreamModel, setLastStreamModel] = useState<string | null>(null);

  const scrollViewportRef = useRef<HTMLDivElement | null>(null);

  const selectedSession = useMemo(() => {
    if (!sessions.length) {
      return null;
    }

    return sessions.find((session) => session.id === selectedSessionId) ?? sessions[0] ?? null;
  }, [selectedSessionId, sessions]);

  const {
    data: messages = [],
    isLoading: isMessagesLoading,
    isFetching: isMessagesFetching,
  } = useMessages(selectedSession?.id ?? null);

  const lastAssistantMessage = useMemo(() => {
    const assistantMessages = messages.filter((message) => message.role === "assistant");
    return assistantMessages.at(-1) ?? null;
  }, [messages]);

  useEffect(() => {
    setChatError(null);
    setStreamingStatus(null);
    setLastStreamModel(null);
  }, [selectedSession?.id]);

  useEffect(() => {
    const viewport = scrollViewportRef.current;

    if (!viewport) {
      return;
    }

    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
  }, [messages, streamingStatus]);

  const handleLoginOut = () => {
    instance.logoutRedirect().catch((logoutError) => {
      console.error("Logout failed:", logoutError);
    });
  };

  const handleCreateSession = () => {
    const title = newSessionTitle.trim();

    createSession.mutate(
      { title: title || null },
      {
        onSuccess: (createdSession) => {
          setNewSessionTitle("");
          setSelectedSessionId(createdSession.id);
        },
      },
    );
  };

  const handleRenameSession = (session: Session) => {
    const nextTitle = window.prompt("Rename session", session.title ?? "");

    if (nextTitle === null) {
      return;
    }

    updateSession.mutate({
      sessionId: session.id,
      body: { title: nextTitle.trim() || null },
    });
  };

  const handleDeleteSession = (sessionId: string) => {
    deleteSession.mutate(sessionId, {
      onSuccess: () => {
        setSessionToDelete(null);

        if (selectedSessionId === sessionId) {
          const nextSession = sessions.find((session) => session.id !== sessionId);
          setSelectedSessionId(nextSession?.id ?? null);
        }
      },
    });
  };

  const handleSendMessage = async () => {
    if (!selectedSession || !activeAccount) {
      return;
    }

    const content = draftMessage.trim();

    if (!content) {
      return;
    }

    const requestSessionId = selectedSession.id;
    const requestMetadata = {
      enable_web_search: webSearchEnabled,
      model: selectedModel,
    };

    const optimisticUserMessage = createOptimisticUserMessage(
      requestSessionId,
      activeUserId,
      content,
    );
    const optimisticAssistantMessage = createOptimisticAssistantMessage(
      requestSessionId,
      activeUserId,
      selectedModel,
    );

    const queryKey = messagesQueryKey(requestSessionId);
    let streamHadError = false;
    let optimisticAssistantInserted = false;

    setChatError(null);
    setStreamingStatus("Starting response…");
    setLastStreamModel(null);
    setDraftMessage("");

    queryClient.setQueryData<Message[]>(queryKey, (existing = []) => [
      ...existing,
      optimisticUserMessage,
    ]);

    try {
      await streamChat(
        instance,
        activeAccount,
        requestSessionId,
        {
          content,
          metadata: requestMetadata,
          tools: [],
        },
        {
          onStart: (event) => {
            const streamModel = typeof event.data.model === "string" ? event.data.model : selectedModel;
            const tools = Array.isArray(event.data.tools)
              ? event.data.tools.filter((tool): tool is string => typeof tool === "string")
              : [];

            optimisticAssistantInserted = true;
            setLastStreamModel(streamModel);
            setStreamingStatus(
              tools.length > 0
                ? `Streaming response with ${tools.join(", ")} enabled…`
                : "Streaming response…",
            );

            queryClient.setQueryData<Message[]>(queryKey, (existing = []) => [
              ...existing,
              {
                ...optimisticAssistantMessage,
                metadata: {
                  ...optimisticAssistantMessage.metadata,
                  model: streamModel,
                  tools,
                },
              },
            ]);
          },
          onDelta: (text) => {
            setStreamingStatus("Assistant is responding…");

            queryClient.setQueryData<Message[]>(queryKey, (existing = []) =>
              existing.map((message) =>
                message.id === optimisticAssistantMessage.id
                  ? { ...message, content: `${message.content}${text}` }
                  : message,
              ),
            );
          },
          onToolCall: (event) => {
            const toolName = typeof event.data.tool_name === "string" ? event.data.tool_name : "tool";
            setStreamingStatus(`Running ${toolName}…`);
          },
          onToolResult: () => {
            setStreamingStatus("Tool finished. Continuing response…");
          },
          onComplete: (event) => {
            const completedMessage = event.data.message as Message | undefined;

            if (completedMessage) {
              queryClient.setQueryData<Message[]>(queryKey, (existing = []) => {
                const withoutOptimisticAssistant = existing.filter(
                  (message) => message.id !== optimisticAssistantMessage.id,
                );
                return [...withoutOptimisticAssistant, completedMessage];
              });
            }

            setStreamingStatus("Response complete.");
          },
          onErrorEvent: (event) => {
            streamHadError = true;
            const message =
              typeof event.data.message === "string"
                ? event.data.message
                : "The assistant response failed.";

            setChatError(message);
            setStreamingStatus(null);

            queryClient.setQueryData<Message[]>(queryKey, (existing = []) =>
              existing.filter((message) => message.id !== optimisticAssistantMessage.id),
            );
          },
          onDone: () => {
            if (!streamHadError) {
              setStreamingStatus("Saved to session history.");
            }
          },
        },
      );
    } catch (error) {
      streamHadError = true;
      const nextError = error instanceof Error ? error.message : "Unable to send the message.";
      setChatError(nextError);
      setStreamingStatus(null);

      queryClient.setQueryData<Message[]>(queryKey, (existing = []) =>
        existing.filter(
          (message) =>
            message.id !== optimisticUserMessage.id && message.id !== optimisticAssistantMessage.id,
        ),
      );
    } finally {
      if (optimisticAssistantInserted || streamHadError) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey }),
          queryClient.invalidateQueries({ queryKey: ["sessions"] }),
        ]);
      }
    }
  };

  const canSendMessage = Boolean(selectedSession && activeAccount && draftMessage.trim()) && !isMessagesFetching;

  return (
    <div className="flex min-h-svh bg-background text-foreground">
      <aside className="flex w-full max-w-sm flex-col border-r bg-sidebar text-sidebar-foreground lg:w-96">
        <div className="flex items-center gap-3 border-b px-4 py-4">
          <div className="flex size-10 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground shadow-sm">
            <MessageSquare className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">agent-86</p>
            <p className="truncate text-xs text-sidebar-foreground/70">Session workspace</p>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" onClick={handleLoginOut}>
                <LogOut className="size-4" />
                <span className="sr-only">Sign out</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Sign out</TooltipContent>
          </Tooltip>
        </div>

        <div className="space-y-3 border-b px-4 py-4">
          <div className="flex items-center gap-3 rounded-xl border bg-sidebar-accent/50 px-3 py-3">
            <Avatar className="size-10">
              <AvatarFallback>{getInitials(activeAccount?.name)}</AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{activeAccount?.name ?? "Signed in"}</p>
              <p className="truncate text-xs text-sidebar-foreground/70">
                {activeAccount?.username ?? activeAccount?.localAccountId ?? "Microsoft Entra"}
              </p>
            </div>
          </div>

          <div className="flex gap-2">
            <Input
              value={newSessionTitle}
              onChange={(event) => setNewSessionTitle(event.target.value)}
              placeholder="New session title"
              className="bg-background"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  handleCreateSession();
                }
              }}
            />
            <Button
              type="button"
              onClick={handleCreateSession}
              disabled={createSession.isPending}
            >
              <Plus className="size-4" />
              New
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-4">
          <div className="mb-3 flex items-center justify-between px-1">
            <h2 className="text-xs font-semibold tracking-wide text-sidebar-foreground/70 uppercase">
              Sessions
            </h2>
            <span className="text-xs text-sidebar-foreground/60">{sessions.length}</span>
          </div>

          <div className="space-y-2">
            {isLoading
              ? Array.from({ length: 6 }).map((_, index) => (
                  <div key={index} className="rounded-xl border border-sidebar-border/60 p-3">
                    <Skeleton className="mb-2 h-4 w-2/3 bg-sidebar-accent" />
                    <Skeleton className="h-3 w-1/2 bg-sidebar-accent" />
                  </div>
                ))
              : null}

            {!isLoading && error ? (
              <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                {(error as Error).message || "Failed to load sessions."}
              </div>
            ) : null}

            {!isLoading && !error && sessions.length === 0 ? (
              <div className="rounded-xl border border-dashed px-4 py-6 text-sm text-sidebar-foreground/70">
                No sessions yet. Create one to begin chatting.
              </div>
            ) : null}

            {sessions.map((session) => (
              <SessionSidebarItem
                key={session.id}
                session={session}
                isActive={selectedSession?.id === session.id}
                onSelect={setSelectedSessionId}
                onRename={handleRenameSession}
                onDelete={(sessionId) => {
                  const nextSession = sessions.find((item) => item.id === sessionId) ?? null;
                  setSessionToDelete(nextSession);
                }}
                isDeleting={deleteSession.isPending && sessionToDelete?.id === session.id}
              />
            ))}
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b px-6 py-4">
          <div>
            <p className="text-xs font-medium tracking-[0.2em] text-muted-foreground uppercase">
              Authenticated workspace
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">
              {selectedSession ? getDisplayTitle(selectedSession) : "Choose a session"}
            </h1>
          </div>

          {selectedSession ? (
            <div className="hidden items-center gap-2 sm:flex">
              <Button
                type="button"
                variant="outline"
                onClick={() => handleRenameSession(selectedSession)}
                disabled={updateSession.isPending}
              >
                <Pencil className="size-4" />
                Rename
              </Button>

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button type="button" variant="outline">
                    <Trash2 className="size-4" />
                    Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete session?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This removes <strong>{getDisplayTitle(selectedSession)}</strong> from your
                      session list.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      variant="destructive"
                      onClick={() => handleDeleteSession(selectedSession.id)}
                    >
                      Delete session
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          ) : null}
        </header>

        <div className="grid flex-1 gap-6 p-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,0.85fr)]">
          <section className="flex min-h-0 flex-col rounded-2xl border bg-card shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-6 py-5">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Conversation</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Persisted per session via the backend message and chat endpoints.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {MODEL_OPTIONS.map((option) => (
                  <Button
                    key={option.value}
                    type="button"
                    variant={selectedModel === option.value ? "default" : "outline"}
                    size="sm"
                    onClick={() => setSelectedModel(option.value)}
                  >
                    <WandSparkles className="size-4" />
                    {option.label}
                  </Button>
                ))}
                <Button
                  type="button"
                  variant={webSearchEnabled ? "default" : "outline"}
                  size="sm"
                  onClick={() => setWebSearchEnabled((current) => !current)}
                >
                  <Sparkles className="size-4" />
                  Web search {webSearchEnabled ? "on" : "off"}
                </Button>
              </div>
            </div>

            <div ref={scrollViewportRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
              {!selectedSession ? (
                <EmptyConversationState />
              ) : isMessagesLoading ? (
                <div className="space-y-4">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <div key={index} className={cn("flex", index % 2 === 0 ? "justify-start" : "justify-end")}>
                      <Skeleton className="h-24 w-full max-w-xl rounded-2xl" />
                    </div>
                  ))}
                </div>
              ) : messages.length === 0 ? (
                <EmptyConversationState />
              ) : (
                <div className="space-y-4">
                  {messages.map((message) => (
                    <MessageBubble key={message.id} message={message} />
                  ))}
                </div>
              )}
            </div>

            <div className="border-t px-6 py-5">
              {chatError ? (
                <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                  {chatError}
                </div>
              ) : null}

              {streamingStatus ? (
                <div className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
                  <LoaderCircle className="size-4 animate-spin" />
                  <span>{streamingStatus}</span>
                </div>
              ) : null}

              <div className="rounded-2xl border bg-background p-3 shadow-xs">
                <textarea
                  value={draftMessage}
                  onChange={(event) => setDraftMessage(event.target.value)}
                  placeholder={
                    selectedSession
                      ? "Ask agent-86 about Azure, architecture, or your next implementation step…"
                      : "Select or create a session to begin chatting."
                  }
                  disabled={!selectedSession || isMessagesFetching}
                  rows={4}
                  className="min-h-28 w-full resize-none border-0 bg-transparent text-sm leading-6 outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void handleSendMessage();
                    }
                  }}
                />

                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t pt-3">
                  <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <span className="rounded-full bg-muted px-2.5 py-1">
                      Model: {selectedModel}
                    </span>
                    <span className="rounded-full bg-muted px-2.5 py-1">
                      Web search: {webSearchEnabled ? "enabled" : "disabled"}
                    </span>
                  </div>

                  <Button type="button" onClick={() => void handleSendMessage()} disabled={!canSendMessage}>
                    <Send className="size-4" />
                    Send message
                  </Button>
                </div>
              </div>
            </div>
          </section>

          <section className="space-y-6">
            <div className="rounded-2xl border bg-card p-6 shadow-sm">
              <p className="text-sm font-medium text-muted-foreground">Authenticated as</p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <Avatar className="size-12">
                  <AvatarFallback>{getInitials(activeAccount?.name)}</AvatarFallback>
                </Avatar>
                <div>
                  <p className="text-base font-semibold">{activeAccount?.name ?? "Unknown user"}</p>
                  <p className="text-sm text-muted-foreground">
                    {activeAccount?.username ?? "No username available"}
                  </p>
                </div>
              </div>

              <Separator className="my-6" />

              <dl className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl border bg-muted/40 p-4">
                  <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Object ID
                  </dt>
                  <dd className="mt-2 break-all text-sm font-medium">
                    {String(activeAccount?.idTokenClaims?.oid ?? "N/A")}
                  </dd>
                </div>
                <div className="rounded-xl border bg-muted/40 p-4">
                  <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Active scope
                  </dt>
                  <dd className="mt-2 break-all text-sm font-medium">
                    {LOGIN_SCOPES[0] ?? "Missing VITE_API_SCOPE"}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="rounded-2xl border bg-card p-6 shadow-sm">
              <p className="text-sm font-medium text-muted-foreground">Session details</p>
              {selectedSession ? (
                <div className="mt-4 space-y-4">
                  <div>
                    <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                      Title
                    </p>
                    <p className="mt-1 text-sm font-medium">{getDisplayTitle(selectedSession)}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                      Session ID
                    </p>
                    <p className="mt-1 break-all text-sm text-muted-foreground">{selectedSession.id}</p>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                        Created
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {formatSessionTimestamp(selectedSession.created_at)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                        Updated
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {formatSessionTimestamp(selectedSession.updated_at)}
                      </p>
                    </div>
                  </div>
                  <Separator />
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="rounded-xl border bg-muted/40 p-4">
                      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                        Messages
                      </p>
                      <p className="mt-2 text-2xl font-semibold">{messages.length}</p>
                    </div>
                    <div className="rounded-xl border bg-muted/40 p-4">
                      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                        Last model
                      </p>
                      <p className="mt-2 text-sm font-medium">
                        {getAssistantModel(lastAssistantMessage) ?? lastStreamModel ?? selectedModel}
                      </p>
                    </div>
                  </div>

                  <div className="rounded-xl border bg-muted/30 p-4">
                    <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                      Assistant tools
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {getAssistantTools(lastAssistantMessage).length > 0 ? (
                        getAssistantTools(lastAssistantMessage).map((tool) => (
                          <span key={tool} className="rounded-full border bg-background px-2.5 py-1 text-xs">
                            {tool}
                          </span>
                        ))
                      ) : (
                        <span className="text-sm text-muted-foreground">No tools used yet.</span>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mt-4 rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
                  Select a session from the sidebar to inspect it here.
                </div>
              )}
            </div>
          </section>
        </div>
      </main>

      <AlertDialog
        open={Boolean(sessionToDelete)}
        onOpenChange={(open) => {
          if (!open) {
            setSessionToDelete(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete session?</AlertDialogTitle>
            <AlertDialogDescription>
              {sessionToDelete ? (
                <>
                  This will permanently remove <strong>{getDisplayTitle(sessionToDelete)}</strong>.
                </>
              ) : (
                "This session will be removed from your workspace."
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (sessionToDelete) {
                  handleDeleteSession(sessionToDelete.id);
                }
              }}
            >
              Delete session
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function SignInScreen() {
  const { instance } = useMsal();

  const handleLogin = () => {
    instance
      .loginRedirect({
        scopes: LOGIN_SCOPES,
      })
      .catch((loginError) => console.error("Login failed:", loginError));
  };

  return (
    <div className="flex min-h-svh items-center justify-center bg-muted/30 px-6 py-12">
      <div className="w-full max-w-md rounded-3xl border bg-card p-8 shadow-sm">
        <div className="mb-8 flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-sm">
          <MessageSquare className="size-6" />
        </div>
        <p className="text-sm font-medium text-muted-foreground">agent-86</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Sign in to your workspace</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          Authenticate with Microsoft Entra ID to access your chat sessions and continue with the
          new sidebar-based application shell.
        </p>

        <div className="mt-8 rounded-2xl border bg-muted/40 p-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">Configured redirect</p>
          <p className="mt-1 break-all">{import.meta.env.VITE_REDIRECT_URI ?? "Not configured"}</p>
        </div>

        <Button className="mt-8 w-full" size="lg" onClick={handleLogin}>
          Sign in with Microsoft
        </Button>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <>
      <UnauthenticatedTemplate>
        <SignInScreen />
      </UnauthenticatedTemplate>

      <AuthenticatedTemplate>
        <AuthenticatedApp />
      </AuthenticatedTemplate>
    </>
  );
}