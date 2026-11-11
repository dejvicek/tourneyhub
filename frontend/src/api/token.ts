// The access token (ADR-006): in memory only, never in localStorage, React
// state or the query cache. A reload starts without one; the session
// refreshes from the cookie.

let accessToken: string | null = null;
// True after this tab logged out: the refresh cookie is gone, so asking the
// API for a session would only get a 401 the browser logs as an error.
let loggedOut = false;
const sessionEndedListeners = new Set<() => void>();

export function getAccessToken(): string | null {
  return accessToken;
}

/** Sets the token after a login or refresh; null forgets it, e.g. on logout. */
export function setAccessToken(token: string | null): void {
  accessToken = token;
  loggedOut = false;
}

/** Forgets the token after a logout, and remembers that no session is left. */
export function forgetSession(): void {
  accessToken = null;
  loggedOut = true;
}

/** Whether this tab logged out and has not logged in since. */
export function isLoggedOut(): boolean {
  return loggedOut;
}

/**
 * Calls `listener` when a refresh fails and the session is over, so the app
 * can go to the login. Returns a function that removes the listener.
 */
export function onSessionEnded(listener: () => void): () => void {
  sessionEndedListeners.add(listener);
  return () => {
    sessionEndedListeners.delete(listener);
  };
}

/** Forgets the token and tells the listeners; the API client calls it. */
export function endSession(): void {
  accessToken = null;
  for (const listener of sessionEndedListeners) {
    listener();
  }
}
