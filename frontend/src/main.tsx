import { createRoot } from 'react-dom/client'
import { MsalProvider } from '@azure/msal-react'
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import { msalInstance, initialize } from './auth/msalConfig.ts'
import './index.css'
import App from './App.tsx'
import { API_BASE_URL } from './api/client.ts'
import { initializeTelemetry } from './telemetry.ts'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

async function bootstrap() {
  try {
    await initializeTelemetry(API_BASE_URL);
    await initialize();
    createRoot(document.getElementById("root")!).render(
      <MsalProvider instance={msalInstance}>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <App />
          </TooltipProvider>
        </QueryClientProvider>
      </MsalProvider>
    );
  } catch (error) {
    console.error("MSAL initialization failed: ", error);
  }
}

bootstrap();