import { type MiddlewareFunction, redirect } from "react-router";

import { getAccessToken } from "@/api/token";

import { restoreSession } from "./api";
import { loginPath } from "./loginPath";

/**
 * Guards the organizer's routes (docs/frontend-style.md §9, FR-003): without
 * a session, and when the refresh cookie cannot restore one, it sends the
 * organizer to the login, which returns here afterwards.
 */
export const requireSession: MiddlewareFunction = async ({ request }) => {
  if (getAccessToken() !== null || (await restoreSession())) {
    return;
  }
  const url = new URL(request.url);
  // eslint-disable-next-line @typescript-eslint/only-throw-error -- a middleware redirects by throwing React Router's Response
  throw redirect(loginPath(`${url.pathname}${url.search}`));
};
