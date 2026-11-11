import { queryOptions, skipToken } from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";

/** The season standings (FR-061, BR-110–BR-113), computed on read. */
export const standingsQueries = {
  season: (leagueId: string, seasonId: string | undefined) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "seasons", seasonId, "standings"],
      queryFn:
        seasonId === undefined
          ? skipToken
          : ({ signal }) =>
              dataOf(
                api.GET(
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
