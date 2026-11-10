import {
  type InferDataFromTag,
  mutationOptions,
  queryOptions,
  skipToken,
} from "@tanstack/react-query";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";
import type {
  DypHalfWrite,
  HalvesMethod,
  SeedingMethod,
  TournamentCreate,
  TournamentFormatWrite,
  TournamentState,
} from "@/demo/contract";

// ---- setup (screens 1-5): provisional routes, see the "setup" section of
// src/demo/contract.ts. Every write sends the target state (ADR-008).

const tournamentPath = (leagueId: string, tournamentId: string) => ({
  params: { path: { league_id: leagueId, tournament_id: tournamentId } },
});

export const setupQueries = {
  /** What setup knows beyond the tournament: picked players, halves, counter. */
  /** Waits while the tournament is not known yet (a new one has no id). */
  detail: (leagueId: string, tournamentId: string | undefined) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "tournaments", tournamentId, "setup"],
      queryFn:
        tournamentId === undefined
          ? skipToken
          : ({ signal }) =>
              dataOf(
                provisionalApi.GET(
                  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup",
                  { ...tournamentPath(leagueId, tournamentId), signal },
                ),
              ),
    }),
  /** The first round or the whole schedule that "Generate and start" would make. */
  preview: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "tournaments", tournamentId, "preview"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/preview",
            { ...tournamentPath(leagueId, tournamentId), signal },
          ),
        ),
    }),
  /** BR-020: the league ranking, with the season points shown beside it. */
  ranking: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "ranking"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET("/api/v1/leagues/{league_id}/ranking", {
            params: { path: { league_id: leagueId } },
            signal,
          }),
        ),
    }),
  players: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "players"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET("/api/v1/leagues/{league_id}/players", {
            params: { path: { league_id: leagueId } },
            signal,
          }),
        ),
    }),
};

/** A write in a league: in order, and followed by a reload of the league (ADR-008). */
function leagueWrite<Variables, Result>(
  leagueId: string,
  write: (variables: Variables) => Promise<Result>,
) {
  return mutationOptions({
    scope: { id: `league:${leagueId}` },
    mutationFn: write,
    onSettled: (_data, _error, _variables, _result, context) =>
      context.client.invalidateQueries({ queryKey: ["leagues", leagueId] }),
  });
}

export const setupMutations = {
  create: (leagueId: string) =>
    leagueWrite(leagueId, (body: TournamentCreate) =>
      dataOf(
        provisionalApi.POST("/api/v1/leagues/{league_id}/tournaments", {
          params: { path: { league_id: leagueId } },
          body,
        }),
      ),
    ),
  format: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (body: TournamentFormatWrite) =>
      dataOf(
        provisionalApi.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/format",
          { ...tournamentPath(leagueId, tournamentId), body },
        ),
      ),
    ),
  players: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (playerIds: string[]) =>
      dataOf(
        provisionalApi.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/players",
          {
            ...tournamentPath(leagueId, tournamentId),
            body: { player_ids: playerIds },
          },
        ),
      ),
    ),
  halves: (leagueId: string, tournamentId: string) =>
    leagueWrite(
      leagueId,
      (body: { method: HalvesMethod; halves: DypHalfWrite[] }) =>
        dataOf(
          provisionalApi.PUT(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/halves",
            { ...tournamentPath(leagueId, tournamentId), body },
          ),
        ),
    ),
  pairs: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (pairs: [string, string][]) =>
      dataOf(
        provisionalApi.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/pairs",
          { ...tournamentPath(leagueId, tournamentId), body: { pairs } },
        ),
      ),
    ),
  topPlayers: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (playerIds: string[]) =>
      dataOf(
        provisionalApi.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/top-players",
          {
            ...tournamentPath(leagueId, tournamentId),
            body: { player_ids: playerIds },
          },
        ),
      ),
    ),
  seeding: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (method: SeedingMethod) =>
      dataOf(
        provisionalApi.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/seeding",
          { ...tournamentPath(leagueId, tournamentId), body: { method } },
        ),
      ),
    ),
  seedOrder: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (entryIds: string[]) =>
      dataOf(
        provisionalApi.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/seed-order",
          {
            ...tournamentPath(leagueId, tournamentId),
            body: { entry_ids: entryIds },
          },
        ),
      ),
    ),
  /** "Draw again" and "Shuffle again": carry the draw counter the screen showed. */
  draw: (leagueId: string, tournamentId: string) =>
    leagueWrite(
      leagueId,
      (body: { expected_draw_counter: number; target: "pairs" | "seeds" }) =>
        dataOf(
          provisionalApi.POST(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/draw",
            { ...tournamentPath(leagueId, tournamentId), body },
          ),
        ),
    ),
  start: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (expectedDrawCounter: number) =>
      dataOf(
        provisionalApi.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/start",
          {
            ...tournamentPath(leagueId, tournamentId),
            body: { expected_draw_counter: expectedDrawCounter },
          },
        ),
      ),
    ),
  /** FR-036: possible until the first result; also used by the running screens. */
  backToSetup: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (expectedState: TournamentState) =>
      dataOf(
        provisionalApi.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/back-to-setup",
          {
            ...tournamentPath(leagueId, tournamentId),
            body: { expected_state: expectedState },
          },
        ),
      ),
    ),
  /** FR-038; a repeated delete answers 404, which also ends in the reload. */
  remove: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, () =>
      dataOf(
        provisionalApi.DELETE(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
          tournamentPath(leagueId, tournamentId),
        ),
      ),
    ),
};

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

/** A tournament as the detail query returns it. */
export type TournamentDetail = InferDataFromTag<
  unknown,
  ReturnType<typeof tournamentQueries.detail>["queryKey"]
>;

/** The schedule the preview query returns. */
export type SchedulePreviewData = InferDataFromTag<
  unknown,
  ReturnType<typeof setupQueries.preview>["queryKey"]
>;
