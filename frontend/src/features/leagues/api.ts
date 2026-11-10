import { queryOptions } from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

// Calls through provisionalApi use routes of the demo's contract
// (src/demo/contract.ts); they move to api once the backend has them.
export const leagueQueries = {
  list: () =>
    queryOptions({
      queryKey: ["leagues"],
      queryFn: ({ signal }) =>
        dataOf(provisionalApi.GET("/api/v1/leagues", { signal })),
    }),
  detail: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET("/api/v1/leagues/{league_id}", {
            params: { path: { league_id: leagueId } },
            signal,
          }),
        ),
    }),
  seasons: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "seasons"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET("/api/v1/leagues/{league_id}/seasons", {
            params: { path: { league_id: leagueId } },
            signal,
          }),
        ),
    }),
  settings: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "settings"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET("/api/v1/leagues/{league_id}/settings", {
            params: { path: { league_id: leagueId } },
            signal,
          }),
        ),
    }),
};
