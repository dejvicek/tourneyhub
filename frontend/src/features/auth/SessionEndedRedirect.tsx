import { useEffect } from "react";
import { Outlet, useLocation, useMatch, useNavigate } from "react-router";

import { onSessionEnded } from "@/api/token";
import { paths } from "@/lib/paths";

import { loginPath } from "./loginPath";

/**
 * When the session ends mid-visit (a refresh that failed, ADR-006), an
 * organizer screen goes to the login and comes back afterwards. Share-link
 * views and the auth screens have no session to lose.
 */
function SessionEndedRedirect() {
  const navigate = useNavigate();
  const location = useLocation();
  const publicLeague = useMatch(paths.publicLeague);
  const publicTournament = useMatch(paths.publicTournament);
  const outside =
    publicLeague !== null ||
    publicTournament !== null ||
    location.pathname === paths.login ||
    location.pathname === paths.signUp ||
    location.pathname === paths.home;
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
      <Outlet />
    </>
  );
}
