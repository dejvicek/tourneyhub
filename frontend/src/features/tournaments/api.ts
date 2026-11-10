import { queryOptions, skipToken } from "@tanstack/react-query";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

// Provisional routes of the demo's contract (src/demo/contract.ts).
export const tournamentQueries = {
  /** Waits while the season is not known yet. */
  ofSeason: (leagueId: string, seasonId: string | undefined) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "seasons", seasonId, "tournaments"],
      queryFn:
        seasonId === undefined
          ? skipToken
          : ({ signal }) =>
              dataOf(
                provisionalApi.GET(
                  "/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments",
                  {
                    params: {
                      path: { league_id: leagueId, season_id: seasonId },
                    },
                    signal,
                  },
                ),
              ),
    }),
  detail: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "tournaments", tournamentId],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
            {
              params: {
                path: { league_id: leagueId, tournament_id: tournamentId },
              },
              signal,
            },
          ),
        ),
    }),
};
