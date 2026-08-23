import type { AccountInfo, IPublicClientApplication } from "@azure/msal-browser";

import { API_BASE_URL, apiFetch, ApiError } from "@/api/client";
import { getApiToken } from "@/auth/getApiToken";
import type {
  Artifact,
  ArtifactAnalysisJob,
  DownloadArtifactResult,
  UploadArtifactRequest,
} from "@/types/artifact";
import { createInteractionId, trackWorkflowEvent, trackWorkflowException } from "@/telemetry";

function getDownloadFilename(response: Response, fallbackFilename: string) {
  const contentDisposition = response.headers.get("content-disposition") ?? "";
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);

  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }

  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return filenameMatch?.[1] ?? fallbackFilename;
}

export const listArtifacts = (
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
) => apiFetch<Artifact[]>(`/sessions/${sessionId}/artifacts`, instance, account);

export async function uploadArtifact(
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
  request: UploadArtifactRequest,
) {
  const interactionId = createInteractionId();
  trackWorkflowEvent("artifact.upload.started", interactionId, { content_type: request.file.type || "unknown" });
  const token = await getApiToken(instance, account);
  const formData = new FormData();
  formData.append("file", request.file);

  if (request.metadata && Object.keys(request.metadata).length > 0) {
    formData.append("metadata", JSON.stringify(request.metadata));
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/artifacts/upload`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "x-agent86-interaction-id": interactionId,
    },
    body: formData,
    });
  } catch (error) {
    trackWorkflowException(error, interactionId);
    throw error;
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    const error = new ApiError(response.status, body || response.statusText);
    trackWorkflowException(error, interactionId);
    throw error;
  }

  const artifact = await response.json() as Artifact;
  trackWorkflowEvent("artifact.upload.completed", interactionId, { content_type: request.file.type || "unknown" });
  return artifact;
}

export async function downloadArtifact(
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
  artifactId: string,
  fallbackFilename = "artifact",
): Promise<DownloadArtifactResult> {
  const token = await getApiToken(instance, account);
  const response = await fetch(
    `${API_BASE_URL}/sessions/${sessionId}/artifacts/${artifactId}/download`,
    {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  );

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(response.status, body || response.statusText);
  }

  const blob = await response.blob();

  return {
    blob,
    filename: getDownloadFilename(response, fallbackFilename),
    contentType: blob.type || response.headers.get("content-type") || "application/octet-stream",
  };
}

export const analyzeArtifact = (
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
  artifactId: string,
) =>
  apiFetch<ArtifactAnalysisJob>(
    `/sessions/${sessionId}/artifacts/${artifactId}/analyze`,
    instance,
    account,
    { method: "POST" },
  );

export const getArtifactAnalysis = (
  instance: IPublicClientApplication,
  account: AccountInfo,
  sessionId: string,
  artifactId: string,
  jobId: string,
) =>
  apiFetch<ArtifactAnalysisJob>(
    `/sessions/${sessionId}/artifacts/${artifactId}/analysis/${jobId}`,
    instance,
    account,
  );