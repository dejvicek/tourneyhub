import type { UIMatch } from "react-router";

/** What a route tells the layouts above it, through its `handle`. */
export interface RouteHandle {
  /**
   * Inside a tournament and its setup the phone hides the league's header
   * and bottom bar (Figma, Bottom nav: "Hide it inside a tournament").
   */
  hidesLeagueChrome?: boolean;
}

function isRouteHandle(handle: unknown): handle is RouteHandle {
  return typeof handle === "object" && handle !== null;
}

/** Whether a matched route asks the league shell to hide its phone chrome. */
export function hidesLeagueChrome(matches: UIMatch[]): boolean {
  return matches.some(
    (match) =>
      isRouteHandle(match.handle) && match.handle.hidesLeagueChrome === true,
  );
}
