import type { IPublicClientApplication, AccountInfo } from "@azure/msal-browser";
import { InteractionRequiredAuthError } from "@azure/msal-browser";

import { getSilentRedirectUri } from "./msalConfig";

const API_SCOPE = import.meta.env.VITE_API_SCOPE;

if (!API_SCOPE) {
  throw new Error("Missing VITE_API_SCOPE. Check frontend/.env.");
}

let interactionInProgress = false;

function isTimedOutError(error: unknown) {
  return typeof error === "object"
    && error !== null
    && "errorCode" in error
    && (error as { errorCode?: string }).errorCode === "timed_out";
}

export async function getApiToken(
  instance: IPublicClientApplication,
  account: AccountInfo
): Promise<string> {
  const request = {
    scopes: [API_SCOPE],
    account,
    redirectUri: getSilentRedirectUri(),
  };

  try {
    const result = await instance.acquireTokenSilent(request);
    return result.accessToken;
  } catch (error) {
    if (error instanceof InteractionRequiredAuthError || isTimedOutError(error)) {
      if (interactionInProgress) {
        // Prevent multiple simultaneous interactive redirects
        throw new Error("Interactive token acquisition already in progress");
      }

      interactionInProgress = true;

      try {
        await instance.loginRedirect({
          scopes: [API_SCOPE],
          redirectUri: import.meta.env.VITE_REDIRECT_URI,
        });
      } finally {
        interactionInProgress = false;
      }

      throw error; // redirect navigates away, this won't continue
    }

    throw error;
  }
}