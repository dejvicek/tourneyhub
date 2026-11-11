import { useEffect } from "react";
import { Outlet, useLocation, useNavigate } from "react-router";

import { onSessionEnded } from "@/api/token";

import { loginPath } from "./loginPath";
import { PasswordChangeRedirect } from "./PasswordChangeRedirect";
import { useOutsideArea } from "./useOutsideArea";

/**
 * When the session ends mid-visit (a refresh that failed, ADR-006), an
 * organizer screen goes to the login and comes back afterwards. Share-link
 * views and the auth screens have no session to lose.
 */
function SessionEndedRedirect() {
  const navigate = useNavigate();
  const location = useLocation();
  const outside = useOutsideArea();
  const here = `${location.pathname}${location.search}`;

  useEffect(() => {
    if (outside) {
      return undefined;
    }
    return onSessionEnded(() => {
      void navigate(loginPath(here), { replace: true });
    });
  }, [outside, here, navigate]);

  return null;
}

/** The root route's layout: the session watch above every screen. */
export function RootWithSession() {
  return (
    <>
      <SessionEndedRedirect />
      <PasswordChangeRedirect />
      <Outlet />
    </>
  );
}
