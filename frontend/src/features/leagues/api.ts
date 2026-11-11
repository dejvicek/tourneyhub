import {
  mutationOptions,
  type QueryClient,
  queryOptions,
} from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";
import type { components } from "@/api/schema";

type LeagueUpdate = components["schemas"]["LeagueUpdate"];

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
  /** The active season's tournaments, for BR-010 before a new season. */
  tournaments: (leagueId: string, seasonId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "seasons", seasonId, "tournaments"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments",
            {
              params: { path: { league_id: leagueId, season_id: seasonId } },
              signal,
            },
          ),
        ),
    }),
};

const scope = (leagueId: string) => ({ id: `league:${leagueId}` });

/** Every write reloads the league's prefix, success or not (ADR-008). */
const reload = (queryClient: QueryClient, leagueId: string) => () =>
  queryClient.invalidateQueries({ queryKey: ["leagues", leagueId] });

export const leagueMutations = {
  /** FR-010: a league with its Season 1; the id is the client's (ADR-008). */
  create: (queryClient: QueryClient) =>
    mutationOptions({
      mutationFn: (league: { id: string; name: string }) =>
        dataOf(api.POST("/api/v1/leagues", { body: league })),
      onSettled: () => queryClient.invalidateQueries({ queryKey: ["leagues"] }),
    }),
  update: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: (update: LeagueUpdate) =>
        dataOf(
          api.PATCH("/api/v1/leagues/{league_id}", {
            params: { path: { league_id: leagueId } },
            body: update,
          }),
        ),
      onSettled: () => queryClient.invalidateQueries({ queryKey: ["leagues"] }),
      scope: scope(leagueId),
    }),
  /** FR-013: everything in the league goes; the confirmation is the UI's. */
  delete: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: () =>
        dataOf(
          api.DELETE("/api/v1/leagues/{league_id}", {
            params: { path: { league_id: leagueId } },
          }),
        ),
      onSettled: () => {
        queryClient.removeQueries({ queryKey: ["leagues", leagueId] });
        return queryClient.invalidateQueries({ queryKey: ["leagues"] });
      },
      scope: scope(leagueId),
    }),
  /** FR-021: closes the active season; carries its number (ADR-008). */
  startSeason: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: (expectedCurrentNumber: number) =>
        dataOf(
          api.POST("/api/v1/leagues/{league_id}/seasons", {
            params: { path: { league_id: leagueId } },
            body: { expected_current_number: expectedCurrentNumber },
          }),
        ),
      onSettled: reload(queryClient, leagueId),
      scope: scope(leagueId),
    }),
  /** FR-020: null restores "Season n"; closed seasons too (BR-011). */
  renameSeason: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: (input: { seasonId: string; name: string | null }) =>
        dataOf(
          api.PUT("/api/v1/leagues/{league_id}/seasons/{season_id}/name", {
            params: {
              path: { league_id: leagueId, season_id: input.seasonId },
            },
            body: { name: input.name },
          }),
        ),
      onSettled: reload(queryClient, leagueId),
      scope: scope(leagueId),
    }),
  /** FR-011, BR-012: the whole table of the active season. */
  setPlacementPoints: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: (input: { seasonId: string; points: number[] }) =>
        dataOf(
          api.PUT(
            "/api/v1/leagues/{league_id}/seasons/{season_id}/placement-points",
            {
              params: {
                path: { league_id: leagueId, season_id: input.seasonId },
              },
              body: { placement_points: input.points },
            },
          ),
        ),
      onSettled: reload(queryClient, leagueId),
      scope: scope(leagueId),
    }),
};
