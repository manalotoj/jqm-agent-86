import { useEffect, useState } from "react";
import { BarChart3, CheckCircle2, LoaderCircle, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAnalyzeArtifact, useArtifactAnalysis } from "@/hooks/useArtifacts";
import type { Artifact, ArtifactAnalysisJob } from "@/types/artifact";

function formatDateTime(value: string | null) {
  if (!value || Number.isNaN(new Date(value).getTime())) {
    return null;
  }

  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function getStatus(job: ArtifactAnalysisJob) {
  switch (job.state) {
    case "completed":
      return { label: "Completed", className: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" };
    case "partial":
      return { label: "Partial", className: "bg-amber-500/10 text-amber-700 dark:text-amber-300" };
    case "failed":
      return { label: "Failed", className: "bg-destructive/10 text-destructive" };
    default:
      return { label: job.state === "running" ? "Running" : "Requested", className: "bg-primary/10 text-primary" };
  }
}

function Findings({ findings }: { findings: Record<string, unknown> }) {
  const entries = Object.entries(findings);

  if (entries.length === 0) {
    return null;
  }

  return (
    <details className="mt-3 rounded-lg border bg-muted/30 px-3 py-2 text-xs">
      <summary className="cursor-pointer font-medium text-muted-foreground">Analysis findings</summary>
      <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-foreground">
        {JSON.stringify(findings, null, 2)}
      </pre>
    </details>
  );
}

export function ArtifactAnalysisPanel({ artifact, sessionId }: { artifact: Artifact; sessionId: string }) {
  const [jobId, setJobId] = useState<string | null>(null);
  const analyzeArtifact = useAnalyzeArtifact(sessionId);
  const analysisQuery = useArtifactAnalysis(sessionId, artifact.id, jobId);
  const job = analysisQuery.data;
  const status = job ? getStatus(job) : null;

  useEffect(() => {
    setJobId(null);
  }, [artifact.id, sessionId]);

  const handleAnalyze = () => {
    analyzeArtifact.mutate(artifact.id, {
      onSuccess: (nextJob) => setJobId(nextJob.id),
    });
  };

  const error = analyzeArtifact.error ?? analysisQuery.error;
  const isActive = job?.state === "requested" || job?.state === "running";

  return (
    <div className="w-full border-t pt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <BarChart3 className="size-4" />
          <span>CSV analysis</span>
          {status ? <span className={`rounded-full px-2 py-0.5 font-medium ${status.className}`}>{status.label}</span> : null}
        </div>
        <Button type="button" variant="outline" size="sm" onClick={handleAnalyze} disabled={analyzeArtifact.isPending || isActive}>
          {analyzeArtifact.isPending || isActive ? <LoaderCircle className="size-4 animate-spin" /> : <BarChart3 className="size-4" />}
          {isActive ? "Analyzing" : job ? "Analyze again" : "Analyze CSV"}
        </Button>
      </div>

      {error ? (
        <p className="mt-2 flex items-center gap-2 text-xs text-destructive"><TriangleAlert className="size-4" />{error.message}</p>
      ) : null}

      {job ? (
        <div className="mt-2 text-xs text-muted-foreground">
          <p>
            Rows: {job.successful_rows}/{job.expected_rows} successful; chunks: {job.successful_chunks}/{job.expected_chunks} successful
            {job.failed_rows > 0 || job.failed_chunks > 0 ? `; ${job.failed_rows} rows and ${job.failed_chunks} chunks failed` : ""}.
          </p>
          {job.claim_expires_at ? <p className="mt-1">Worker lease expires {formatDateTime(job.claim_expires_at)}.</p> : null}
          {job.error_detail ? <p className="mt-1 text-destructive">{job.error_detail}</p> : null}
          {job.state === "completed" ? <p className="mt-1 flex items-center gap-1 text-emerald-700 dark:text-emerald-300"><CheckCircle2 className="size-3.5" />Analysis complete.</p> : null}
          <Findings findings={job.findings} />
        </div>
      ) : null}
    </div>
  );
}