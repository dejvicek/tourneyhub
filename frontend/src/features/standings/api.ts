import { queryOptions, skipToken } from "@tanstack/react-query";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";
import { providesProvisionalRoutes } from "@/lib/demoMode";

// Provisional route of the demo's contract (src/demo/contract.ts); the backend
// serves it with P10, so it is off outside demo mode.
export const standingsQueries = {
  season: (leagueId: string, seasonId: string | undefined) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "seasons", seasonId, "standings"],
      enabled: providesProvisionalRoutes(),
      queryFn:
        seasonId === undefined
          ? skipToken
          : ({ signal }) =>
              dataOf(
                provisionalApi.GET(
                  "/api/v1/leagues/{league_id}/seasons/{season_id}/standings",
                  {
                    params: {
                      path: { league_id: leagueId, season_id: seasonId },
                    },
                    signal,
                  },
                ),
              ),
    }),
};
