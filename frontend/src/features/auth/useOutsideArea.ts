import { useLocation, useMatch } from "react-router";

import { paths } from "@/lib/paths";

/**
 * True on the screens that have no session to watch: share-link views, the
 * login, the sign-up and the home page.
 */
export function useOutsideArea(): boolean {
  const location = useLocation();
  const publicLeague = useMatch(paths.publicLeague);
  const publicTournament = useMatch(paths.publicTournament);
  return (
    publicLeague !== null ||
    publicTournament !== null ||
    location.pathname === paths.login ||
    location.pathname === paths.signUp ||
    location.pathname === paths.home
  );
}
