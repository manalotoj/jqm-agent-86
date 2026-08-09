import { PublicClientApplication } from '@azure/msal-browser'
import type { Configuration } from '@azure/msal-browser'

const CLIENT_ID = import.meta.env.VITE_ENTRA_CLIENT_ID;
const TENANT_ID = import.meta.env.VITE_ENTRA_TENANT_ID;
const REDIRECT_URI = import.meta.env.VITE_REDIRECT_URI;

if (!CLIENT_ID || !TENANT_ID) {
  throw new Error(
    "Missing VITE_ENTRA_CLIENT_ID or VITE_ENTRA_TENANT_ID. Check frontend/.env."
  );
}

export const msalConfig: Configuration = {
  auth: {
    clientId: CLIENT_ID,
    authority: `https://login.microsoftonline.com/${TENANT_ID}`,
    redirectUri: REDIRECT_URI,
    postLogoutRedirectUri: REDIRECT_URI,
  },
  cache: {
    cacheLocation: "localStorage",
  },
};

export const msalInstance = new PublicClientApplication(msalConfig);