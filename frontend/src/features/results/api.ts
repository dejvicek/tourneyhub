import { mutationOptions } from "@tanstack/react-query";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";
import type { ResultWrite } from "@/demo/contract";

// Provisional routes of the demo's contract (src/demo/contract.ts). Each
// write reloads the league's data (ADR-008).
export const resultMutations = {
  /** A whole result, every game or the walkover; the empty one clears it (FR-050–FR-053). */
  save: (leagueId: string, tournamentId: string, matchId: string) =>
    mutationOptions({
      mutationFn: (body: ResultWrite) =>
        dataOf(
          provisionalApi.PUT(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/matches/{match_id}/result",
            {
              params: {
                path: {
                  league_id: leagueId,
                  tournament_id: tournamentId,
                  match_id: matchId,
                },
              },
              body,
            },
          ),
        ),
      scope: { id: `league:${leagueId}` },
      onSettled: (_data, _error, _variables, _result, { client }) =>
        client.invalidateQueries({ queryKey: ["leagues", leagueId] }),
    }),
  /** Finishes after the round robin: its standings become the places (FR-040). */
  finish: (leagueId: string, tournamentId: string) =>
    mutationOptions({
      mutationFn: () =>
        dataOf(
          provisionalApi.POST(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/finish",
            {
              params: {
                path: { league_id: leagueId, tournament_id: tournamentId },
              },
              body: { expected_state: "in_progress" },
            },
          ),
        ),
      scope: { id: `league:${leagueId}` },
      onSettled: (_data, _error, _variables, _result, { client }) =>
        client.invalidateQueries({ queryKey: ["leagues", leagueId] }),
    }),
};
