import type { IPublicClientApplication, AccountInfo } from "@azure/msal-browser";
import { InteractionRequiredAuthError } from "@azure/msal-browser";

const API_SCOPE = import.meta.env.VITE_API_SCOPE;

if (!API_SCOPE) {
  throw new Error("Missing VITE_API_SCOPE. Check frontend/.env.");
}

export async function getApiToken(
  instance: IPublicClientApplication,
  account: AccountInfo
): Promise<string> {
  const request = { scopes: [API_SCOPE], account };

  try {
    const result = await instance.acquireTokenSilent(request);
    return result.accessToken;
  } catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
      // Silent acquisition failed (expired session, revoked consent, etc.)
      // — fall back to interactive.
      await instance.acquireTokenRedirect(request);
      // acquireTokenRedirect navigates away; nothing after this executes
      // on this pass. The caller will retry after redirect completes.
      throw error;
    }
    throw error;
  }
}