import { useParams } from "react-router";

type RouteParam = "leagueId" | "tournamentId" | "matchId" | "shareToken";

/**
 * A path parameter the current route always has. useParams types every
 * parameter as optional (docs/frontend-style.md §9); this narrows it once.
 */
export function useRouteParam(name: RouteParam): string {
  const value = useParams()[name];
  if (value === undefined) {
    throw new Error(`The route has no :${name} parameter`);
  }
  return value;
}
