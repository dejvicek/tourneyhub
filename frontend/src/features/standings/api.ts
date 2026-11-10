import { queryOptions, skipToken } from "@tanstack/react-query";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

// Provisional route of the demo's contract (src/demo/contract.ts).
export const standingsQueries = {
  season: (leagueId: string, seasonId: string | undefined) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "seasons", seasonId, "standings"],
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
