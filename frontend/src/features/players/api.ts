import {
  mutationOptions,
  type QueryClient,
  queryOptions,
} from "@tanstack/react-query";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

// Players mirror P5b (feat/players), still provisional until it merges
// (src/demo/contract.ts, players).
export const playerQueries = {
  list: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "players"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET("/api/v1/leagues/{league_id}/players", {
            // The screen lists removed players too, to restore them (P5b).
            params: {
              path: { league_id: leagueId },
              query: { include_removed: true },
            },
            signal,
          }),
        ),
    }),
};

const scope = (leagueId: string) => ({ id: `league:${leagueId}` });

export const playerMutations = {
  /** FR-012; a taken name, a removed player's too, is 422 with its holder. */
  add: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: (name: string) =>
        dataOf(
          provisionalApi.POST("/api/v1/leagues/{league_id}/players", {
            params: { path: { league_id: leagueId } },
            body: { name },
          }),
        ),
      onSettled: () =>
        queryClient.invalidateQueries({ queryKey: ["leagues", leagueId] }),
      scope: scope(leagueId),
    }),
  /** FR-012: a rename shows everywhere, past results too. */
  rename: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: (input: { playerId: string; name: string }) =>
        dataOf(
          provisionalApi.PUT(
            "/api/v1/leagues/{league_id}/players/{player_id}/name",
            {
              params: {
                path: { league_id: leagueId, player_id: input.playerId },
              },
              body: { name: input.name },
            },
          ),
        ),
      onSettled: () =>
        queryClient.invalidateQueries({ queryKey: ["leagues", leagueId] }),
      scope: scope(leagueId),
    }),
  /** BR-002: removed or back, a target state (ADR-008). */
  setRemoved: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: (input: { playerId: string; removed: boolean }) =>
        dataOf(
          provisionalApi.PUT(
            "/api/v1/leagues/{league_id}/players/{player_id}/removed",
            {
              params: {
                path: { league_id: leagueId, player_id: input.playerId },
              },
              body: { removed: input.removed },
            },
          ),
        ),
      onSettled: () =>
        queryClient.invalidateQueries({ queryKey: ["leagues", leagueId] }),
      scope: scope(leagueId),
    }),
};
