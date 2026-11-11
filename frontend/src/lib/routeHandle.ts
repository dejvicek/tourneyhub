import type { UIMatch } from "react-router";

import type { paths } from "./paths";

/** What a route tells the layouts above it, through its `handle`. */
export interface RouteHandle {
  /**
   * Inside a tournament and its setup the phone hides the league's header
   * and bottom bar (Figma, Bottom nav: "Hide it inside a tournament").
   */
  hidesLeagueChrome?: boolean;
  /**
   * The tournament screen a route is; the tournament's guard sends the
   * organizer to the tournament's own path when the tournament's state has
   * no such screen (a deep link to the wrong phase).
   */
  screen?: keyof typeof paths;
}

function isRouteHandle(handle: unknown): handle is RouteHandle {
  return typeof handle === "object" && handle !== null;
}

/** The tournament screen of the deepest matched route that names one. */
export function tournamentScreenOf(
  matches: UIMatch[],
): keyof typeof paths | undefined {
  return matches
    .map((match) =>
      isRouteHandle(match.handle) ? match.handle.screen : undefined,
    )
    .findLast((screen) => screen !== undefined);
}

/** Whether a matched route asks the league shell to hide its phone chrome. */
export function hidesLeagueChrome(matches: UIMatch[]): boolean {
  return matches.some(
    (match) =>
      isRouteHandle(match.handle) && match.handle.hidesLeagueChrome === true,
  );
}
