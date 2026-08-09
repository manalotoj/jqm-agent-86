import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MsalProvider } from '@azure/msal-react' // [1] Import the provider
import { msalInstance } from './auth/msalConfig.ts' // [2] Import your initialized instance
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import './index.css'
import App from './App.tsx'

// ...existing imports

const queryClient = new QueryClient();

msalInstance.initialize().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <MsalProvider instance={msalInstance}>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </MsalProvider>
    </StrictMode>
  );
}).catch((error: unknown) => {
  console.error("MSAL initialization failed: ", error);
});