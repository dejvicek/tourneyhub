import {
  mutationOptions,
  type QueryClient,
  queryOptions,
} from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";

export const playerQueries = {
  list: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "players"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET("/api/v1/leagues/{league_id}/players", {
            // The screen lists removed players too, to restore them.
            params: {
              path: { league_id: leagueId },
              query: { include_removed: true },
            },
            signal,
          }),
        ),
    }),
  /**
   * BR-002: the unfinished tournaments a player is in, which block removing
   * them. Asked when the remove dialog opens, so it can say so up front.
   */
  unfinishedTournaments: (
    leagueId: string,
    playerId: string,
    enabled: boolean,
  ) =>
    queryOptions({
      queryKey: [
        "leagues",
        leagueId,
        "players",
        playerId,
        "unfinished-tournaments",
      ],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/leagues/{league_id}/players/{player_id}/tournaments",
            {
              params: { path: { league_id: leagueId, player_id: playerId } },
              signal,
            },
          ),
        ),
      enabled,
    }),
};

const scope = (leagueId: string) => ({ id: `league:${leagueId}` });

export const playerMutations = {
  /** FR-012; a taken name, a removed player's too, is 422 with its holder. */
  add: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: (name: string) =>
        dataOf(
          api.POST("/api/v1/leagues/{league_id}/players", {
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
          api.PUT("/api/v1/leagues/{league_id}/players/{player_id}/name", {
            params: {
              path: { league_id: leagueId, player_id: input.playerId },
            },
            body: { name: input.name },
          }),
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
          api.PUT("/api/v1/leagues/{league_id}/players/{player_id}/removed", {
            params: {
              path: { league_id: leagueId, player_id: input.playerId },
            },
            body: { removed: input.removed },
          }),
        ),
      onSettled: () =>
        queryClient.invalidateQueries({ queryKey: ["leagues", leagueId] }),
      scope: scope(leagueId),
    }),
};
