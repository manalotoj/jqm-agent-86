import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MsalProvider } from '@azure/msal-react'
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import { msalInstance } from './auth/msalConfig.ts'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient();

msalInstance.initialize().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <MsalProvider instance={msalInstance}>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <App />
          </TooltipProvider>
        </QueryClientProvider>
      </MsalProvider>
    </StrictMode>
  );
}).catch((error: unknown) => {
  console.error("MSAL initialization failed: ", error);
});