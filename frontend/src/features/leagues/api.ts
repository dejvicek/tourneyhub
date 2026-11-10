import { queryOptions } from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";

function league(leagueId: string, signal: AbortSignal) {
  return dataOf(
    api.GET("/api/v1/leagues/{league_id}", {
      params: { path: { league_id: leagueId } },
      signal,
    }),
  );
}

export const leagueQueries = {
  list: () =>
    queryOptions({
      queryKey: ["leagues"],
      queryFn: ({ signal }) => dataOf(api.GET("/api/v1/leagues", { signal })),
    }),
  /** The league with its settings, share token and seasons (LeagueRead). */
  detail: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId],
      queryFn: ({ signal }) => league(leagueId, signal),
    }),
  /** The league's seasons, oldest first; the same query as `detail`. */
  seasons: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId],
      queryFn: ({ signal }) => league(leagueId, signal),
      select: (data) => data.seasons,
    }),
};
