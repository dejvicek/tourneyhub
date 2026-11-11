import { mutationOptions, queryOptions } from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";
import type { components } from "@/api/schema";

type PlacementsWrite = components["schemas"]["PlacementsWrite"];

// The play screens' read, the league's players and the field writes all come
// from the generated API (P9). The read lives here with the field writes: the
// lint rules let only a feature's top-level api.ts call the API.

interface TournamentPath {
  league_id: string;
  tournament_id: string;
}

function path(leagueId: string, tournamentId: string): TournamentPath {
  return { league_id: leagueId, tournament_id: tournamentId };
}

export const playQueries = {
  /** Waiting order, live standings and the phase's end (FR-060, FR-092). */
  view: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "tournaments", tournamentId, "play"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/play",
            { params: { path: path(leagueId, tournamentId) }, signal },
          ),
        ),
    }),
  /** The league's players, for the names on matches. */
  players: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "players"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET("/api/v1/leagues/{league_id}/players", {
            params: { path: { league_id: leagueId } },
            signal,
          }),
        ),
    }),
};

// Writes send target states (ADR-008); each reloads the league's data.
export const fieldMutations = {
  /** Places, moves, swaps or takes off matches (FR-093). */
  place: (leagueId: string, tournamentId: string) =>
    mutationOptions({
      mutationFn: (body: PlacementsWrite) =>
        dataOf(
          api.PUT(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields/placements",
            { params: { path: path(leagueId, tournamentId) }, body },
          ),
        ),
      scope: { id: `league:${leagueId}` },
      onSettled: (_data, _error, _variables, _result, { client }) =>
        client.invalidateQueries({ queryKey: ["leagues", leagueId] }),
    }),
  /** Adds the field with the number it expects to get (BR-132). */
  add: (leagueId: string, tournamentId: string) =>
    mutationOptions({
      mutationFn: (number: number) =>
        dataOf(
          api.POST(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields",
            {
              params: { path: path(leagueId, tournamentId) },
              body: { number },
            },
          ),
        ),
      scope: { id: `league:${leagueId}` },
      onSettled: (_data, _error, _variables, _result, { client }) =>
        client.invalidateQueries({ queryKey: ["leagues", leagueId] }),
    }),
  /** Removes a field by its id (BR-132). */
  remove: (leagueId: string, tournamentId: string) =>
    mutationOptions({
      mutationFn: (fieldId: string) =>
        dataOf(
          api.DELETE(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields/{field_id}",
            {
              params: {
                path: { ...path(leagueId, tournamentId), field_id: fieldId },
              },
            },
          ),
        ),
      scope: { id: `league:${leagueId}` },
      onSettled: (_data, _error, _variables, _result, { client }) =>
        client.invalidateQueries({ queryKey: ["leagues", leagueId] }),
    }),
};
