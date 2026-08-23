import { ApplicationInsights } from "@microsoft/applicationinsights-web";

type RuntimeConfig = {
  applicationInsightsConnectionString: string | null;
  telemetryEnabled: boolean;
  logLevel: string;
};

let appInsights: ApplicationInsights | undefined;

function sanitizeError(error: unknown): Error {
  if (error instanceof Error) {
    return new Error(error.name || "Error");
  }
  return new Error("UnknownError");
}

export async function initializeTelemetry(apiBaseUrl: string): Promise<void> {
  let config: RuntimeConfig;
  try {
    const response = await fetch(`${apiBaseUrl}/runtime-config`);
    if (!response.ok) return;
    config = (await response.json()) as RuntimeConfig;
  } catch {
    return;
  }

  if (!config.telemetryEnabled || !config.applicationInsightsConnectionString) return;

  appInsights = new ApplicationInsights({
    config: {
      connectionString: config.applicationInsightsConnectionString,
      enableAutoRouteTracking: false,
      enableCorsCorrelation: true,
      distributedTracingMode: 1,
      disableFetchTracking: false,
      disableAjaxTracking: false,
    },
  });
  appInsights.loadAppInsights();
  appInsights.trackPageView({ name: document.title || "agent-86" });

  window.addEventListener("error", (event) => {
    appInsights?.trackException({ exception: sanitizeError(event.error) });
  });
  window.addEventListener("unhandledrejection", (event) => {
    appInsights?.trackException({ exception: sanitizeError(event.reason) });
  });
}

export function createInteractionId(): string {
  return crypto.randomUUID();
}

export function trackWorkflowEvent(name: string, interactionId: string, properties: Record<string, string> = {}): void {
  appInsights?.trackEvent({ name }, { interaction_id: interactionId, ...properties });
}

export function trackWorkflowException(error: unknown, interactionId: string): void {
  appInsights?.trackException({ exception: sanitizeError(error) }, { interaction_id: interactionId });
}