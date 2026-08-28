import { useState } from "react";
import { Check, ClipboardCopy, LoaderCircle, RefreshCw, Sparkles, WandSparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useGenerateContextSummary } from "@/hooks/useSessionSummary";
import type { SessionSummary } from "@/types/sessionSummary";

function formatDateTime(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function SummaryPill({ label }: { label: string }) {
  return (
    <span className="rounded-full border bg-background px-2.5 py-1 text-xs font-medium text-muted-foreground">
      {label}
    </span>
  );
}

function SectionList({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div>
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</p>
      <ul className="mt-2 space-y-2 text-sm text-foreground">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <span className="mt-1 size-1.5 shrink-0 rounded-full bg-primary" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SummaryLoadingState() {
  return (
    <div className="mt-4 space-y-4">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-16 w-full rounded-xl" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
      <Skeleton className="h-28 w-full rounded-xl" />
    </div>
  );
}

function EmptySummaryState({
  onGenerate,
  isGenerating,
}: {
  onGenerate: () => void;
  isGenerating: boolean;
}) {
  return (
    <div className="mt-4 rounded-xl border border-dashed bg-muted/20 px-4 py-5 text-sm">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-primary/10 p-2 text-primary">
          <Sparkles className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-foreground">No summary generated yet</p>
          <p className="mt-1 leading-6 text-muted-foreground">
            Generate a structured recap of the session so decisions, action items, tools, and
            referenced artifacts are easier to revisit later.
          </p>
          <Button
            type="button"
            variant="outline"
            className="mt-4"
            onClick={onGenerate}
            disabled={isGenerating}
          >
            {isGenerating ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <WandSparkles className="size-4" />
            )}
            Generate summary
          </Button>
        </div>
      </div>
    </div>
  );
}

function ActionItemStatus({ status }: { status: SessionSummary["action_items"][number]["status"] }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[11px] font-medium capitalize",
        status === "done" && "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        status === "open" && "bg-amber-500/10 text-amber-700 dark:text-amber-300",
        status === "abandoned" && "bg-muted text-muted-foreground",
      )}
    >
      {status}
    </span>
  );
}

function ContinuationContextBlock({
  text,
  sessionId,
}: {
  text: string;
  sessionId: string;
}) {
  const [copied, setCopied] = useState(false);
  const contextSummary = useGenerateContextSummary(sessionId);

  async function handleCopy() {
    try {
      // Always fetch a fresh context summary from the live session so the
      // model can draw on the full conversation, then copy the result.
      const fresh = await contextSummary.mutateAsync();
      await navigator.clipboard.writeText(fresh);
    } catch {
      // Fall back to the stored continuation_context if the live call fails.
      await navigator.clipboard.writeText(text);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-xl border bg-muted/20 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Continue in new session
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 px-2 text-xs"
          onClick={handleCopy}
          disabled={contextSummary.isPending}
        >
          {contextSummary.isPending ? (
            <>
              <LoaderCircle className="size-3.5 animate-spin" />
              Generating…
            </>
          ) : copied ? (
            <>
              <Check className="size-3.5 text-emerald-500" />
              <span className="text-emerald-500">Copied</span>
            </>
          ) : (
            <>
              <ClipboardCopy className="size-3.5" />
              Copy to resume
            </>
          )}
        </Button>
      </div>
      <p className="mt-3 text-sm leading-6 whitespace-pre-wrap text-foreground">{text}</p>
    </div>
  );
}

function SummaryContent({ summary }: { summary: SessionSummary }) {
  return (
    <div className="mt-4 space-y-5">
      <div className="rounded-xl border bg-muted/30 p-4">
        <p className="text-sm font-semibold text-foreground">{summary.title}</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{summary.one_line_summary}</p>
      </div>

      <ContinuationContextBlock
        text={summary.continuation_context}
        sessionId={summary.session_id}
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border bg-background p-4">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Coverage
          </p>
          <p className="mt-2 text-sm text-foreground">{formatDateTime(summary.date_range_start)}</p>
          <p className="mt-1 text-xs text-muted-foreground">through {formatDateTime(summary.date_range_end)}</p>
        </div>
        <div className="rounded-xl border bg-background p-4">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Last updated
          </p>
          <p className="mt-2 text-sm text-foreground">{formatDateTime(summary.updated_at)}</p>
          <p className="mt-1 text-xs text-muted-foreground">Created {formatDateTime(summary.created_at)}</p>
        </div>
      </div>

      {summary.tags.length > 0 ? (
        <div>
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Tags</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {summary.tags.map((tag) => (
              <SummaryPill key={tag} label={tag} />
            ))}
          </div>
        </div>
      ) : null}

      {summary.topics.length > 0 ? (
        <div>
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Topics</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {summary.topics.map((topic) => (
              <SummaryPill key={topic} label={topic} />
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-2">
        <SectionList title="Key decisions" items={summary.key_decisions} />
        <SectionList title="Open questions" items={summary.open_questions} />
      </div>

      {summary.action_items.length > 0 ? (
        <div>
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Action items
          </p>
          <div className="mt-2 space-y-2">
            {summary.action_items.map((actionItem, index) => (
              <div key={`${actionItem.description}-${index}`} className="rounded-xl border bg-background p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <ActionItemStatus status={actionItem.status} />
                  {actionItem.owner ? (
                    <span className="text-xs text-muted-foreground">Owner: {actionItem.owner}</span>
                  ) : null}
                </div>
                <p className="mt-2 text-sm text-foreground">{actionItem.description}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {summary.artifacts_generated.length > 0 ? (
        <div>
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Artifacts referenced
          </p>
          <div className="mt-2 space-y-2">
            {summary.artifacts_generated.map((artifact) => (
              <div key={`${artifact.location}-${artifact.name}`} className="rounded-xl border bg-background p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <SummaryPill label={artifact.artifact_type} />
                  <p className="text-sm font-medium text-foreground">{artifact.name}</p>
                </div>
                <p className="mt-2 break-all text-xs text-muted-foreground">{artifact.location}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {summary.tools_used.length > 0 ? (
        <div>
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Tools used</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {summary.tools_used.map((toolName) => (
              <SummaryPill key={toolName} label={toolName} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function SessionSummaryCard({
  summary,
  isLoading,
  isGenerating,
  errorMessage,
  hasSession,
  onGenerate,
  generateLabel,
}: {
  summary: SessionSummary | null | undefined;
  isLoading: boolean;
  isGenerating: boolean;
  errorMessage: string | null;
  hasSession: boolean;
  onGenerate: () => void;
  generateLabel?: string;
}) {
  const actionLabel = generateLabel ?? (summary ? "Regenerate summary" : "Generate summary");

  return (
    <div className="rounded-2xl border bg-card p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-muted-foreground">Session summary</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Structured recap of what happened in this chat session.
          </p>
        </div>

        {hasSession && summary ? (
          <Button type="button" variant="outline" size="sm" onClick={onGenerate} disabled={isGenerating}>
            {isGenerating ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
            {actionLabel}
          </Button>
        ) : null}
      </div>

      {!hasSession ? (
        <div className="mt-4 rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
          Select a session from the sidebar to inspect its summary here.
        </div>
      ) : isLoading ? (
        <SummaryLoadingState />
      ) : errorMessage ? (
        <div className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {errorMessage}
        </div>
      ) : summary ? (
        <>
          <SummaryContent summary={summary} />
          <Separator className="my-5" />
          <p className="text-xs text-muted-foreground">
            Summary ID: <span className="break-all">{summary.id}</span>
          </p>
        </>
      ) : (
        <EmptySummaryState onGenerate={onGenerate} isGenerating={isGenerating} />
      )}
    </div>
  );
}