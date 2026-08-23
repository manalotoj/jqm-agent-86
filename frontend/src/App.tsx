import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import { getActiveAccountOrFirst, isAuthReady } from "./auth/msalConfig";

import { useQueryClient } from "@tanstack/react-query";
import {
  AuthenticatedTemplate,
  UnauthenticatedTemplate,
  useMsal,
} from "@azure/msal-react";
import {
  Bot,
  CheckCircle2,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  PanelLeft,
  PanelRight,
  Download,
  FileUp,
  LoaderCircle,
  LogOut,
  MessageSquare,
  MoreHorizontal,
  Paperclip,
  Pencil,
  Plus,
  Send,
  Sparkles,
  TriangleAlert,
  Trash2,
  User,
  WandSparkles,
  X,
} from "lucide-react";

import { streamChat } from "@/api/chat";
import { MarkdownMessage } from "@/components/MarkdownMessage";
import { ArtifactAnalysisPanel } from "@/components/ArtifactAnalysisPanel";
import { SessionSummaryCard } from "@/components/SessionSummaryCard";
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
import { downloadArtifact } from "@/api/artifacts";
import { useArtifacts, useUploadArtifact } from "@/hooks/useArtifacts";
import { useMessages, messagesQueryKey } from "@/hooks/useMessages";
import { useGenerateSessionSummary, useSessionSummary } from "@/hooks/useSessionSummary";
import {
  useCreateSession,
  useDeleteSession,
  useSessions,
  useUpdateSession,
} from "@/hooks/useSessions";
import { cn } from "@/lib/utils";
import {
  loadComposerPreferences,
  saveComposerPreferences,
  type ComposerModel,
} from "@/lib/composerPreferences";
import type { Artifact } from "@/types/artifact";
import type { Message } from "@/types/message";
import type { Session } from "@/types/session";

const LOGIN_SCOPES = [import.meta.env.VITE_API_SCOPE].filter(
  (scope): scope is string => Boolean(scope),
);

const DEFAULT_CHAT_MODEL = "gpt-4.1-mini";
const PREMIUM_CHAT_MODEL = "gpt-5.4";
const EMPTY_MESSAGES: Message[] = [];
const EMPTY_ARTIFACTS: Artifact[] = [];
const EMPTY_SESSIONS: Session[] = [];
const LARGE_MESSAGE_CHARACTER_THRESHOLD = 2_000;
const LARGE_MESSAGE_PREVIEW_CHARACTER_COUNT = 500;
const AUTO_SCROLL_BOTTOM_THRESHOLD = 120;

type NoticeTone = "success" | "error" | "info";
type MainContentView = "chat" | "summary";
type LongMessageDisplayMode = "default" | "expanded" | "collapsed";

type AppNotice = {
  id: string;
  message: string;
  tone: NoticeTone;
};

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

function getMessagePreview(content: string) {
  const normalized = content.replace(/\s+/g, " ").trim();

  if (normalized.length <= LARGE_MESSAGE_PREVIEW_CHARACTER_COUNT) {
    return normalized;
  }

  return `${normalized.slice(0, LARGE_MESSAGE_PREVIEW_CHARACTER_COUNT).trimEnd()}…`;
}

function getAssistantTools(message: Message | null) {
  const tools = message?.metadata?.tools;
  return Array.isArray(tools) ? tools.filter((tool): tool is string => typeof tool === "string") : [];
}

function getMessageArtifactIds(message: Message | null) {
  const artifactIds = message?.metadata?.artifact_ids;

  if (!Array.isArray(artifactIds)) {
    return [];
  }

  return Array.from(
    new Set(artifactIds.filter((artifactId): artifactId is string => typeof artifactId === "string" && Boolean(artifactId.trim()))),
  );
}

function formatArtifactSize(sizeBytes: number) {
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }

  const units = ["KB", "MB", "GB", "TB"];
  let value = sizeBytes / 1024;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function getToastStyles(tone: NoticeTone) {
  switch (tone) {
    case "success":
      return {
        container: "border-emerald-500/30 bg-emerald-500/10 text-emerald-900 dark:text-emerald-100",
        icon: <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-300" />,
      };
    case "error":
      return {
        container: "border-destructive/30 bg-destructive/10 text-destructive",
        icon: <TriangleAlert className="size-4" />,
      };
    default:
      return {
        container: "border-border bg-card text-foreground",
        icon: <Paperclip className="size-4 text-muted-foreground" />,
      };
  }
}

function ToastViewport({
  notices,
  onDismiss,
}: {
  notices: AppNotice[];
  onDismiss: (noticeId: string) => void;
}) {
  if (notices.length === 0) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed top-4 right-4 z-50 flex w-full max-w-sm flex-col gap-3 px-4 sm:px-0">
      {notices.map((notice) => {
        const styles = getToastStyles(notice.tone);

        return (
          <div
            key={notice.id}
            role="status"
            aria-live="polite"
            className={cn(
              "pointer-events-auto flex items-start gap-3 rounded-2xl border px-4 py-3 shadow-lg backdrop-blur-sm",
              styles.container,
            )}
          >
            <div className="mt-0.5 shrink-0">{styles.icon}</div>
            <div className="min-w-0 flex-1 text-sm">{notice.message}</div>
            <button
              type="button"
              onClick={() => onDismiss(notice.id)}
              className="rounded-md p-1 text-current/70 transition-colors hover:bg-black/5 hover:text-current dark:hover:bg-white/10"
            >
              <X className="size-4" />
              <span className="sr-only">Dismiss notification</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}

function createOptimisticUserMessage(
  sessionId: string,
  userId: string,
  content: string,
  artifactIds: string[] = [],
): Message {
  const timestamp = new Date().toISOString();

  return {
    id: `optimistic-user-${crypto.randomUUID()}`,
    session_id: sessionId,
    user_id: userId,
    role: "user",
    content,
    metadata: artifactIds.length > 0 ? { artifact_ids: artifactIds } : {},
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

function MessageBubble({
  message,
  attachedArtifacts,
  onDownloadArtifact,
  downloadingArtifactId,
  longMessageDisplayMode,
  isStreaming,
}: {
  message: Message;
  attachedArtifacts: Artifact[];
  onDownloadArtifact: (artifact: Artifact) => void;
  downloadingArtifactId: string | null;
  longMessageDisplayMode: LongMessageDisplayMode;
  isStreaming: boolean;
}) {
  const isUser = message.role === "user";
  const isLargeAssistantMessage =
    !isUser && message.content.length >= LARGE_MESSAGE_CHARACTER_THRESHOLD;
  const [isCopied, setIsCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(() => !isLargeAssistantMessage || isStreaming);
  const shouldRenderMessageDetails = !isLargeAssistantMessage || isExpanded;
  const model = getAssistantModel(message);
  const tools = getAssistantTools(message);
  const artifactIds = getMessageArtifactIds(message);
  const resolvedArtifacts = artifactIds
    .map((artifactId) => attachedArtifacts.find((artifact) => artifact.id === artifactId) ?? null)
    .filter((artifact): artifact is Artifact => artifact !== null);

  useEffect(() => {
    if (!isLargeAssistantMessage || isStreaming || longMessageDisplayMode === "expanded") {
      setIsExpanded(true);
      return;
    }

    if (longMessageDisplayMode === "collapsed") {
      setIsExpanded(false);
    }
  }, [isLargeAssistantMessage, isStreaming, longMessageDisplayMode, message.id]);

  const handleCopy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(message.content);
          setIsCopied(true);
          window.setTimeout(() => setIsCopied(false), 2_000);
          return;
        } catch {
          // Fall back to the legacy copy mechanism when clipboard permission is denied.
        }
      }

      const textArea = document.createElement("textarea");
      textArea.value = message.content;
      textArea.setAttribute("readonly", "");
      textArea.className = "fixed -left-full top-0 opacity-0";
      document.body.append(textArea);
      textArea.select();
      const wasCopied = document.execCommand("copy");
      textArea.remove();

      if (!wasCopied) {
        throw new Error("The browser could not copy the message.");
      }

      setIsCopied(true);
      window.setTimeout(() => setIsCopied(false), 2_000);
    } catch {
      setIsCopied(false);
    }
  };

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
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  className={cn("ml-auto", isUser && "text-primary-foreground hover:bg-primary-foreground/10 hover:text-primary-foreground")}
                  aria-label={`Copy ${isUser ? "user" : "assistant"} message`}
                  onClick={() => {
                    void handleCopy();
                  }}
                >
                  {isCopied ? <Check className="size-3" /> : <Copy className="size-3" />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{isCopied ? "Copied" : "Copy message"}</TooltipContent>
            </Tooltip>
          </div>
          {isUser ? (
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-primary-foreground">
              {message.content || "…"}
            </p>
          ) : isLargeAssistantMessage && !isExpanded ? (
            <div className="mt-2">
              <p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                {getMessagePreview(message.content)}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className="text-xs text-muted-foreground">
                  {message.content.length.toLocaleString()} characters
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="xs"
                  aria-expanded={false}
                  onClick={() => setIsExpanded(true)}
                >
                  <ChevronDown className="size-3" />
                  Expand message
                </Button>
              </div>
            </div>
          ) : message.content ? (
            <>
              <MarkdownMessage content={message.content} />
              {isLargeAssistantMessage ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  className="mt-2"
                  aria-expanded={true}
                  onClick={() => setIsExpanded(false)}
                >
                  <ChevronUp className="size-3" />
                  Collapse message
                </Button>
              ) : null}
            </>
          ) : (
            <p className="mt-2 text-sm leading-6">…</p>
          )}
          {isUser && resolvedArtifacts.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {resolvedArtifacts.map((artifact) => {
                const isDownloading = downloadingArtifactId === artifact.id;

                return (
                  <button
                    key={artifact.id}
                    type="button"
                    onClick={() => onDownloadArtifact(artifact)}
                    disabled={isDownloading}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] transition-colors",
                      isUser
                        ? "border-primary-foreground/20 bg-primary-foreground/10 text-primary-foreground hover:bg-primary-foreground/15"
                        : "bg-muted/60 text-muted-foreground hover:bg-muted",
                    )}
                  >
                    {isDownloading ? (
                      <LoaderCircle className="size-3 animate-spin" />
                    ) : (
                      <Paperclip className="size-3" />
                    )}
                    <span>{artifact.filename}</span>
                    <span className="rounded-full bg-black/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-current/80 dark:bg-white/10">
                      {formatArtifactSize(artifact.size_bytes)}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : null}
          {shouldRenderMessageDetails && !isUser && tools.length > 0 ? (
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
    <div className="flex h-full items-center justify-center rounded-2xl border border-dashed bg-muted/20 px-6 py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Sparkles className="size-5" />
      </div>
    </div>
  );
}

function AuthenticatedApp() {
  const { instance } = useMsal();
  const activeAccount = getActiveAccountOrFirst();
  const activeUserId = String(
    activeAccount?.idTokenClaims?.oid ?? activeAccount?.localAccountId ?? "current-user",
  );
  const queryClient = useQueryClient();

  const { data: sessions = EMPTY_SESSIONS, isLoading, error } = useSessions();
  const createSession = useCreateSession();
  const updateSession = useUpdateSession();
  const deleteSession = useDeleteSession();

  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [newSessionTitle, setNewSessionTitle] = useState("");
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [draftMessage, setDraftMessage] = useState("");
  const [selectedModel, setSelectedModel] = useState<ComposerModel>(
    () => loadComposerPreferences(activeUserId).selectedModel,
  );
  const [webSearchEnabled, setWebSearchEnabled] = useState(
    () => loadComposerPreferences(activeUserId).webSearchEnabled,
  );
  const [chatError, setChatError] = useState<string | null>(null);
  const [streamingStatus, setStreamingStatus] = useState<string | null>(null);
  const [isStreamingActive, setIsStreamingActive] = useState(false);
  const [lastStreamModel, setLastStreamModel] = useState<string | null>(null);
  const [longMessageDisplayMode, setLongMessageDisplayMode] =
    useState<LongMessageDisplayMode>("default");

  const scrollViewportRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);

  const selectedSession = useMemo(() => {
    if (!sessions.length) {
      return null;
    }

    return sessions.find((session) => session.id === selectedSessionId) ?? sessions[0] ?? null;
  }, [selectedSessionId, sessions]);

  const {
    data: messages = EMPTY_MESSAGES,
    isLoading: isMessagesLoading,
    isFetching: isMessagesFetching,
  } = useMessages(selectedSession?.id ?? null);
  const {
    data: artifacts = EMPTY_ARTIFACTS,
    isLoading: isArtifactsLoading,
    error: artifactsError,
  } = useArtifacts(selectedSession?.id ?? null);
  const {
    data: sessionSummary,
    isLoading: isSessionSummaryLoading,
    error: sessionSummaryError,
  } = useSessionSummary(selectedSession?.id ?? null);
  const uploadArtifact = useUploadArtifact(selectedSession?.id ?? null);
  const generateSessionSummary = useGenerateSessionSummary(selectedSession?.id ?? null);

  const lastAssistantMessage = useMemo(() => {
    const assistantMessages = messages.filter((message) => message.role === "assistant");
    return assistantMessages.at(-1) ?? null;
  }, [messages]);
  const artifactMap = useMemo(
    () => new Map(artifacts.map((artifact) => [artifact.id, artifact] as const)),
    [artifacts],
  );

  useEffect(() => {
    setChatError(null);
    setStreamingStatus(null);
    setIsStreamingActive(false);
    setLastStreamModel(null);
    setLongMessageDisplayMode("default");
    shouldAutoScrollRef.current = true;
  }, [selectedSession?.id]);

  useEffect(() => {
    setMainContentView("chat");
    setIsRegenerateSummaryDialogOpen(false);
  }, [selectedSession?.id]);

  const [selectedArtifactIds, setSelectedArtifactIds] = useState<string[]>([]);
  const [artifactActionError, setArtifactActionError] = useState<string | null>(null);
  const [downloadingArtifactId, setDownloadingArtifactId] = useState<string | null>(null);
  const [notices, setNotices] = useState<AppNotice[]>([]);
  const [isArtifactDragActive, setIsArtifactDragActive] = useState(false);
  const [mainContentView, setMainContentView] = useState<MainContentView>("chat");
  const [isRegenerateSummaryDialogOpen, setIsRegenerateSummaryDialogOpen] = useState(false);
  const [isLeftPaneOpen, setIsLeftPaneOpen] = useState(true);
  const [isRightPaneOpen, setIsRightPaneOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const dismissNotice = (noticeId: string) => {
    setNotices((current) => current.filter((notice) => notice.id !== noticeId));
  };

  const addNotice = (message: string, tone: NoticeTone = "info") => {
    const noticeId = crypto.randomUUID();

    setNotices((current) => [...current.slice(-2), { id: noticeId, message, tone }]);
  };

  useEffect(() => {
    const preferences = loadComposerPreferences(activeUserId);

    setSelectedModel(preferences.selectedModel);
    setWebSearchEnabled(preferences.webSearchEnabled);
  }, [activeUserId]);

  const handleSelectedModelChange = (model: ComposerModel) => {
    setSelectedModel(model);
    saveComposerPreferences(activeUserId, { selectedModel: model, webSearchEnabled });
  };

  const handleWebSearchToggle = () => {
    const nextWebSearchEnabled = !webSearchEnabled;

    setWebSearchEnabled(nextWebSearchEnabled);
    saveComposerPreferences(activeUserId, {
      selectedModel,
      webSearchEnabled: nextWebSearchEnabled,
    });
  };

  useEffect(() => {
    setSelectedArtifactIds((current) => {
      const next = current.filter((artifactId) => artifactMap.has(artifactId));

      if (next.length === current.length && next.every((artifactId, index) => artifactId === current[index])) {
        return current;
      }

      return next;
    });
  }, [artifactMap]);

  useEffect(() => {
    setArtifactActionError(null);
  }, [selectedSession?.id]);

  useEffect(() => {
    if (notices.length === 0) {
      return;
    }

    const timeoutIds = notices.map((notice) =>
      window.setTimeout(() => {
        setNotices((current) => current.filter((item) => item.id !== notice.id));
      }, 4000),
    );

    return () => {
      timeoutIds.forEach((timeoutId) => window.clearTimeout(timeoutId));
    };
  }, [notices]);

  useEffect(() => {
    const viewport = scrollViewportRef.current;

    if (!viewport || !shouldAutoScrollRef.current) {
      return;
    }

    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
  }, [messages, streamingStatus]);

  const handleConversationScroll = () => {
    const viewport = scrollViewportRef.current;

    if (!viewport) {
      return;
    }

    shouldAutoScrollRef.current =
      viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= AUTO_SCROLL_BOTTOM_THRESHOLD;
  };

  const hasLargeAssistantMessages = messages.some(
    (message) =>
      message.role === "assistant" && message.content.length >= LARGE_MESSAGE_CHARACTER_THRESHOLD,
  );

  const handleLoginOut = () => {
    queryClient.clear();

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

  const handleToggleArtifactSelection = (artifactId: string) => {
    setSelectedArtifactIds((current) =>
      current.includes(artifactId)
        ? current.filter((currentArtifactId) => currentArtifactId !== artifactId)
        : [...current, artifactId],
    );

    const artifact = artifactMap.get(artifactId);

    if (artifact) {
      addNotice(
        selectedArtifactIds.includes(artifactId)
          ? `${artifact.filename} removed from the next message.`
          : `${artifact.filename} attached to the next message.`,
        "info",
      );
    }
  };

  const uploadSelectedFile = async (file: File) => {
    if (!selectedSession) {
      return;
    }

    setArtifactActionError(null);

    try {
      const artifact = await uploadArtifact.mutateAsync({ file });
      setSelectedArtifactIds((current) =>
        current.includes(artifact.id) ? current : [...current, artifact.id],
      );
      addNotice(`${artifact.filename} uploaded and attached to the next message.`, "success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to upload the selected artifact.";
      setArtifactActionError(message);
      addNotice(message, "error");
    }
  };

  const handleUploadArtifact = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    if (!selectedSession || !file) {
      return;
    }

    try {
      await uploadSelectedFile(file);
    } finally {
      event.target.value = "";
    }
  };

  const handleArtifactDragState = (event: DragEvent<HTMLDivElement>, nextState: boolean) => {
    event.preventDefault();
    event.stopPropagation();

    if (!selectedSession || uploadArtifact.isPending) {
      return;
    }

    setIsArtifactDragActive(nextState);
  };

  const handleArtifactDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsArtifactDragActive(false);

    if (!selectedSession || uploadArtifact.isPending) {
      return;
    }

    const file = event.dataTransfer.files?.[0];

    if (!file) {
      addNotice("Drop a file to upload it to this session.", "info");
      return;
    }

    await uploadSelectedFile(file);
  };

  const handleDownloadArtifact = async (artifact: Artifact) => {
    if (!selectedSession || !activeAccount) {
      return;
    }

    setArtifactActionError(null);
    setDownloadingArtifactId(artifact.id);

    try {
      const result = await downloadArtifact(
        instance,
        activeAccount,
        selectedSession.id,
        artifact.id,
        artifact.filename,
      );
      const objectUrl = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = result.filename;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      addNotice(`${result.filename} download started.`, "success");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to download the selected artifact.";
      setArtifactActionError(message);
      addNotice(message, "error");
    } finally {
      setDownloadingArtifactId(null);
    }
  };

  const handleGenerateSessionSummary = () => {
    if (!selectedSession) {
      return;
    }

    generateSessionSummary.mutate(undefined, {
      onSuccess: () => {
        addNotice("Session summary updated.", "success");
      },
      onError: (error) => {
        const message =
          error instanceof Error ? error.message : "Unable to generate the session summary.";
        addNotice(message, "error");
      },
    });
  };

  const handleRequestSessionSummaryGeneration = () => {
    if (!selectedSession) {
      return;
    }

    if (sessionSummary) {
      setIsRegenerateSummaryDialogOpen(true);
      return;
    }

    handleGenerateSessionSummary();
  };

  const handleSendMessage = async () => {
    if (!selectedSession || !activeAccount) {
      return;
    }

    const content = draftMessage.trim();
    const artifactIds = selectedArtifactIds.filter((artifactId) => artifactMap.has(artifactId));

    if (!content) {
      return;
    }

    shouldAutoScrollRef.current = true;

    const requestSessionId = selectedSession.id;
    const requestMetadata = {
      enable_web_search: webSearchEnabled,
      model: selectedModel,
      ...(artifactIds.length > 0 ? { artifact_ids: artifactIds } : {}),
    };

    const optimisticUserMessage = createOptimisticUserMessage(
      requestSessionId,
      activeUserId,
      content,
      artifactIds,
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
    setIsStreamingActive(true);
    setLastStreamModel(null);
    setDraftMessage("");
    setSelectedArtifactIds([]);

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
            setIsStreamingActive(false);
          },
          onErrorEvent: (event) => {
            streamHadError = true;
            const message =
              typeof event.data.message === "string"
                ? event.data.message
                : "The assistant response failed.";

            setChatError(message);
            setStreamingStatus(null);
            setIsStreamingActive(false);

            queryClient.setQueryData<Message[]>(queryKey, (existing = []) =>
              existing.filter((message) => message.id !== optimisticAssistantMessage.id),
            );
          },
          onDone: () => {
            if (!streamHadError) {
              setStreamingStatus("Saved to session history.");
              setIsStreamingActive(false);
            }
          },
        },
      );
    } catch (error) {
      streamHadError = true;
      const nextError = error instanceof Error ? error.message : "Unable to send the message.";
      setChatError(nextError);
      setStreamingStatus(null);
      setIsStreamingActive(false);

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

  const canSendMessage =
    Boolean(selectedSession && activeAccount && draftMessage.trim()) &&
    !isMessagesFetching &&
    !uploadArtifact.isPending;

  return (
    <>
      <ToastViewport notices={notices} onDismiss={dismissNotice} />
      <div className="flex min-h-svh bg-background text-foreground">
        <div className="flex border-r bg-sidebar text-sidebar-foreground">
          {!isLeftPaneOpen ? (
            <div className="flex w-14 flex-col items-center gap-3 px-2 py-4">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Expand sessions pane"
                    onClick={() => setIsLeftPaneOpen(true)}
                  >
                    <PanelLeft className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Show sessions</TooltipContent>
              </Tooltip>
            </div>
          ) : null}

          <aside
            className={cn(
              "overflow-hidden border-r bg-sidebar text-sidebar-foreground transition-[width,opacity] duration-200",
              isLeftPaneOpen
                ? "flex w-full max-w-sm flex-col opacity-100 lg:w-96"
                : "w-0 border-r-0 opacity-0",
            )}
          >
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
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Collapse sessions pane"
                    onClick={() => setIsLeftPaneOpen(false)}
                  >
                    <PanelLeft className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Hide sessions</TooltipContent>
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
        </div>

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

          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  aria-label={isLeftPaneOpen ? "Collapse sessions pane" : "Expand sessions pane"}
                  onClick={() => setIsLeftPaneOpen((current) => !current)}
                >
                  <PanelLeft className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{isLeftPaneOpen ? "Hide sessions" : "Show sessions"}</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  aria-label={isRightPaneOpen ? "Collapse details pane" : "Expand details pane"}
                  onClick={() => setIsRightPaneOpen((current) => !current)}
                >
                  <PanelRight className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{isRightPaneOpen ? "Hide details" : "Show details"}</TooltipContent>
            </Tooltip>

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
          </div>
        </header>

        <div
          className={cn(
            "grid min-h-0 flex-1 gap-6 p-6",
            isRightPaneOpen
              ? "lg:grid-cols-[minmax(0,1.6fr)_minmax(320px,0.85fr)]"
              : "grid-cols-1",
          )}
        >
          <section className="flex min-h-0 min-w-0 flex-col rounded-2xl border bg-card shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-6 py-5">
              <div>
                <p className="text-sm font-medium text-muted-foreground">
                  {mainContentView === "chat" ? "Conversation" : "Session summary"}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {mainContentView === "chat"
                    ? "Persisted per session via the backend message and chat endpoints."
                    : "Structured recap of what happened in this chat session."}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {mainContentView === "chat" && hasLargeAssistantMessages ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setLongMessageDisplayMode((current) =>
                        current === "collapsed" ? "expanded" : "collapsed",
                      )
                    }
                  >
                    {longMessageDisplayMode === "collapsed" ? (
                      <ChevronDown className="size-4" />
                    ) : (
                      <ChevronUp className="size-4" />
                    )}
                    {longMessageDisplayMode === "collapsed"
                      ? "Expand all long messages"
                      : "Collapse long messages"}
                  </Button>
                ) : null}
                <div className="inline-flex rounded-full border bg-muted/40 p-1">
                  <Button
                    type="button"
                    variant={mainContentView === "chat" ? "secondary" : "ghost"}
                    size="sm"
                    className="rounded-full"
                    onClick={() => setMainContentView("chat")}
                  >
                    <MessageSquare className="size-4" />
                    Chat
                  </Button>
                  <Button
                    type="button"
                    variant={mainContentView === "summary" ? "secondary" : "ghost"}
                    size="sm"
                    className="rounded-full"
                    onClick={() => setMainContentView("summary")}
                  >
                    <Sparkles className="size-4" />
                    Summary
                  </Button>
                </div>

                {mainContentView === "chat" ? (
                  <div className="flex flex-wrap gap-2">
                    {MODEL_OPTIONS.map((option) => (
                      <Button
                        key={option.value}
                        type="button"
                        variant={selectedModel === option.value ? "default" : "outline"}
                        size="sm"
                        onClick={() => handleSelectedModelChange(option.value)}
                      >
                        <WandSparkles className="size-4" />
                        {option.label}
                      </Button>
                    ))}
                    <Button
                      type="button"
                      variant={webSearchEnabled ? "default" : "outline"}
                      size="sm"
                      onClick={handleWebSearchToggle}
                    >
                      <Sparkles className="size-4" />
                      Web search {webSearchEnabled ? "on" : "off"}
                    </Button>
                  </div>
                ) : null}
              </div>
            </div>

            <div
              ref={mainContentView === "chat" ? scrollViewportRef : undefined}
              onScroll={mainContentView === "chat" ? handleConversationScroll : undefined}
              className="min-h-0 flex-1 overflow-y-auto px-6 py-6"
            >
              {mainContentView === "chat" ? (
                !selectedSession ? (
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
                      <MessageBubble
                        key={message.id}
                        message={message}
                        attachedArtifacts={artifacts}
                        onDownloadArtifact={(artifact) => {
                          void handleDownloadArtifact(artifact);
                        }}
                        downloadingArtifactId={downloadingArtifactId}
                        longMessageDisplayMode={longMessageDisplayMode}
                        isStreaming={
                          isStreamingActive && message.id === lastAssistantMessage?.id
                        }
                      />
                    ))}
                  </div>
                )
              ) : (
                <SessionSummaryCard
                  summary={sessionSummary}
                  isLoading={isSessionSummaryLoading}
                  isGenerating={generateSessionSummary.isPending}
                  errorMessage={sessionSummaryError instanceof Error ? sessionSummaryError.message : null}
                  hasSession={Boolean(selectedSession)}
                  onGenerate={handleRequestSessionSummaryGeneration}
                  generateLabel={sessionSummary ? "Regenerate summary" : "Generate summary"}
                />
              )}
            </div>

            <div className={cn("border-t px-6 py-5", mainContentView !== "chat" && "hidden")}>
              {artifactActionError ? (
                <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                  {artifactActionError}
                </div>
              ) : null}

              {chatError ? (
                <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                  {chatError}
                </div>
              ) : null}

              {streamingStatus ? (
                <div className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
                  {isStreamingActive ? (
                    <LoaderCircle className="size-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="size-4 text-emerald-600" />
                  )}
                  <span>{streamingStatus}</span>
                </div>
              ) : null}

              <div
                className={cn(
                  "rounded-2xl border bg-background p-3 shadow-xs transition-colors",
                  isArtifactDragActive && "border-primary bg-primary/5 ring-2 ring-primary/20",
                )}
                onDragEnter={(event) => handleArtifactDragState(event, true)}
                onDragOver={(event) => handleArtifactDragState(event, true)}
                onDragLeave={(event) => handleArtifactDragState(event, false)}
                onDrop={(event) => {
                  void handleArtifactDrop(event);
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  onChange={(event) => {
                    void handleUploadArtifact(event);
                  }}
                />

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

                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>
                    Drag and drop a file here, or use upload to add a session artifact.
                  </span>
                  {isArtifactDragActive ? (
                    <span className="rounded-full bg-primary/10 px-2.5 py-1 font-medium text-primary">
                      Release to upload
                    </span>
                  ) : null}
                </div>

                {selectedArtifactIds.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {selectedArtifactIds.map((artifactId) => {
                      const artifact = artifactMap.get(artifactId);

                      if (!artifact) {
                        return null;
                      }

                      return (
                        <button
                          key={artifact.id}
                          type="button"
                          onClick={() => handleToggleArtifactSelection(artifact.id)}
                          className="inline-flex items-center gap-2 rounded-full border bg-muted px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted/80"
                        >
                          <Paperclip className="size-3" />
                          <span>{artifact.filename}</span>
                          <span className="rounded-full bg-background px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                            {formatArtifactSize(artifact.size_bytes)}
                          </span>
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-primary">
                            Attached
                          </span>
                          <span aria-hidden="true">×</span>
                          <span className="sr-only">Remove attachment</span>
                        </button>
                      );
                    })}
                  </div>
                ) : null}

                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t pt-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={!selectedSession || uploadArtifact.isPending}
                    >
                      {uploadArtifact.isPending ? (
                        <LoaderCircle className="size-4 animate-spin" />
                      ) : (
                        <FileUp className="size-4" />
                      )}
                      Upload artifact
                    </Button>
                    <span className="rounded-full bg-muted px-2.5 py-1">
                      Model: {selectedModel}
                    </span>
                    <span className="rounded-full bg-muted px-2.5 py-1">
                      Web search: {webSearchEnabled ? "enabled" : "disabled"}
                    </span>
                    <span className="rounded-full bg-muted px-2.5 py-1">
                      Attachments: {selectedArtifactIds.length}
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
          <section
            className={cn(
              "min-w-0 space-y-6",
              isRightPaneOpen ? "block" : "hidden",
            )}
          >
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
                        Artifacts
                      </p>
                      <p className="mt-2 text-2xl font-semibold">{artifacts.length}</p>
                    </div>
                  </div>

                  <div className="rounded-xl border bg-muted/30 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                          Session artifacts
                        </p>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Upload, attach, or download files scoped to this session.
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploadArtifact.isPending}
                      >
                        {uploadArtifact.isPending ? (
                          <LoaderCircle className="size-4 animate-spin" />
                        ) : (
                          <FileUp className="size-4" />
                        )}
                        Upload
                      </Button>
                    </div>

                    {isArtifactsLoading ? (
                      <div className="mt-4 space-y-2">
                        {Array.from({ length: 3 }).map((_, index) => (
                          <Skeleton key={index} className="h-12 w-full rounded-xl" />
                        ))}
                      </div>
                    ) : artifactsError ? (
                      <div className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                        {(artifactsError as Error).message || "Failed to load artifacts."}
                      </div>
                    ) : artifacts.length > 0 ? (
                      <div className="mt-4 space-y-2">
                        {artifacts.map((artifact) => {
                          const isSelected = selectedArtifactIds.includes(artifact.id);
                          const isDownloading = downloadingArtifactId === artifact.id;

                          return (
                            <div
                              key={artifact.id}
                              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-background px-3 py-3"
                            >
                              <button
                                type="button"
                                onClick={() => handleToggleArtifactSelection(artifact.id)}
                                className="min-w-0 flex-1 text-left"
                              >
                                <div className="flex items-center gap-2">
                                  <Paperclip className="size-4 text-muted-foreground" />
                                  <p className="truncate text-sm font-medium">{artifact.filename}</p>
                                  {isSelected ? (
                                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
                                      Attached
                                    </span>
                                  ) : null}
                                </div>
                                <p className="mt-1 text-xs text-muted-foreground">
                                  {artifact.content_type} • {formatArtifactSize(artifact.size_bytes)}
                                </p>
                              </button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  void handleDownloadArtifact(artifact);
                                }}
                                disabled={isDownloading}
                              >
                                {isDownloading ? (
                                  <LoaderCircle className="size-4 animate-spin" />
                                ) : (
                                  <Download className="size-4" />
                                )}
                                Download
                              </Button>
                              {selectedSession ? (
                                <ArtifactAnalysisPanel artifact={artifact} sessionId={selectedSession.id} />
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="mt-4 rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
                        No artifacts uploaded for this session yet.
                      </div>
                    )}
                  </div>

                  <div className="rounded-xl border bg-muted/40 p-4">
                    <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                      Last model
                    </p>
                    <p className="mt-2 text-sm font-medium">
                      {getAssistantModel(lastAssistantMessage) ?? lastStreamModel ?? selectedModel}
                    </p>
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
        open={isRegenerateSummaryDialogOpen}
        onOpenChange={setIsRegenerateSummaryDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Overwrite existing summary?</AlertDialogTitle>
            <AlertDialogDescription>
              Regenerating will replace the current saved session summary with a newly generated one.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setIsRegenerateSummaryDialogOpen(false);
                handleGenerateSessionSummary();
              }}
            >
              Regenerate summary
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={Boolean(sessionToDelete)}
        onOpenChange={(open: boolean) => {
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
    </>
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
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    setAuthReady(isAuthReady());
  }, []);

  if (!authReady) {
    return <div>Loading authentication...</div>;
  }

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