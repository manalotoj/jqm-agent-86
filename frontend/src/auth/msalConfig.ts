import { PublicClientApplication } from '@azure/msal-browser'
import type { Configuration } from '@azure/msal-browser'

const CLIENT_ID = import.meta.env.VITE_ENTRA_CLIENT_ID;
const TENANT_ID = import.meta.env.VITE_ENTRA_TENANT_ID;
const REDIRECT_URI = import.meta.env.VITE_REDIRECT_URI;
const SILENT_REDIRECT_URI = new URL("/blank.html", window.location.origin).toString();

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
  system: {
    iframeBridgeTimeout: 20_000,
    redirectNavigationTimeout: 20_000,
  },
};

export const msalInstance = new PublicClientApplication(msalConfig);

let msalInitialized = false;

export async function initialize() {
  try {
    await msalInstance.initialize();

    // Handle redirect response and set active account if possible
    const redirectResponse = await msalInstance.handleRedirectPromise();

    if (redirectResponse?.account) {
      msalInstance.setActiveAccount(redirectResponse.account);
    } else {
      const currentActive = msalInstance.getActiveAccount();
      if (!currentActive) {
        const allAccounts = msalInstance.getAllAccounts();
        if (allAccounts.length > 0) {
          msalInstance.setActiveAccount(allAccounts[0]);
        }
      }
    }

    msalInitialized = true;
  } catch (error) {
    console.error("MSAL initialize error:", error);
    throw error;
  }
}

export function isAuthReady() {
  return msalInitialized;
}

export function getActiveAccountOrFirst() {
  return msalInstance.getActiveAccount() ?? msalInstance.getAllAccounts()[0] ?? null;
}

export function getSilentRedirectUri() {
  return SILENT_REDIRECT_URI;
}