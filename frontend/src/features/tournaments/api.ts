import {
  type InferDataFromTag,
  mutationOptions,
  queryOptions,
  skipToken,
} from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";
import type { components } from "@/api/schema";

type Schemas = components["schemas"];

// ---- setup (screens 1-5). The backend serves the setup, "Generate and
// start", "Back to setup" and the schedule preview; the top players are still
// a provisional route (the "setup" section of src/demo/contract.ts). Every
// write sends the target state or the state it expects (ADR-008).

const tournamentPath = (leagueId: string, tournamentId: string) => ({
  params: { path: { league_id: leagueId, tournament_id: tournamentId } },
});

export const setupQueries = {
  /**
   * What setup knows: the format, the picks, the halves, the entries, the
   * league ranking and the draw counter. Waits while the tournament is not
   * known yet (a new one has no id).
   */
  detail: (leagueId: string, tournamentId: string | undefined) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "tournaments", tournamentId, "setup"],
      queryFn:
        tournamentId === undefined
          ? skipToken
          : ({ signal }) =>
              dataOf(
                api.GET(
                  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup",
                  { ...tournamentPath(leagueId, tournamentId), signal },
                ),
              ),
    }),
  /**
   * The schedule that "Generate and start" would make, or the reason it would
   * not, with the draw counter the start must carry (FR-035).
   */
  preview: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "tournaments", tournamentId, "preview"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/preview",
            { ...tournamentPath(leagueId, tournamentId), signal },
          ),
        ),
    }),
  /** The league's players on the list, for their names. */
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
    leagueWrite(leagueId, (body: Schemas["TournamentCreate"]) =>
      dataOf(
        api.POST("/api/v1/leagues/{league_id}/tournaments", {
          params: { path: { league_id: leagueId } },
          body,
        }),
      ),
    ),
  format: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (body: Schemas["TournamentFormatWrite"]) =>
      dataOf(
        api.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/format",
          { ...tournamentPath(leagueId, tournamentId), body },
        ),
      ),
    ),
  players: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (playerIds: string[]) =>
      dataOf(
        api.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/players",
          {
            ...tournamentPath(leagueId, tournamentId),
            body: { player_ids: playerIds },
          },
        ),
      ),
    ),
  halves: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (body: Schemas["HalvesWrite"]) =>
      dataOf(
        api.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/halves",
          { ...tournamentPath(leagueId, tournamentId), body },
        ),
      ),
    ),
  pairs: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (pairs: [string, string][]) =>
      dataOf(
        api.PUT(
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
    leagueWrite(leagueId, (method: Schemas["SeedingMethod"]) =>
      dataOf(
        api.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/seeding",
          { ...tournamentPath(leagueId, tournamentId), body: { method } },
        ),
      ),
    ),
  seedOrder: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (entryIds: string[]) =>
      dataOf(
        api.PUT(
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
    leagueWrite(leagueId, (body: Schemas["DrawWrite"]) =>
      dataOf(
        api.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/draw",
          { ...tournamentPath(leagueId, tournamentId), body },
        ),
      ),
    ),
  /**
   * FR-035: carries the draw counter and the seed order the review showed
   * (409 when stale).
   */
  start: (leagueId: string, tournamentId: string) =>
    leagueWrite(leagueId, (body: Schemas["StartWrite"]) =>
      dataOf(
        api.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/start",
          { ...tournamentPath(leagueId, tournamentId), body },
        ),
      ),
    ),
  /** FR-036: possible until the first result; also used by the running screens. */
  backToSetup: (leagueId: string, tournamentId: string) =>
    leagueWrite(
      leagueId,
      (expectedState: Schemas["BackToSetupWrite"]["expected_state"]) =>
        dataOf(
          api.POST(
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
    mutationOptions({
      scope: { id: `league:${leagueId}` },
      mutationFn: () =>
        dataOf(
          api.DELETE(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
            tournamentPath(leagueId, tournamentId),
          ),
        ),
      // Reloads the league without the deleted tournament's own queries,
      // which would only answer 404, then forgets them.
      onSettled: async (_data, _error, _variables, _result, { client }) => {
        const own = ["leagues", leagueId, "tournaments", tournamentId];
        await client.invalidateQueries({
          queryKey: ["leagues", leagueId],
          predicate: (query) =>
            !own.every((part, index) => query.queryKey[index] === part),
        });
        client.removeQueries({ queryKey: own });
      },
    }),
};

export const tournamentQueries = {
  /** A season's tournaments with their progress (screen 1). Waits while the season is not known yet. */
  ofSeason: (leagueId: string, seasonId: string | undefined) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "seasons", seasonId, "tournaments"],
      queryFn:
        seasonId === undefined
          ? skipToken
          : ({ signal }) =>
              dataOf(
                api.GET(
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
  /** The whole tournament with its rounds, fields and waiting matches. */
  detail: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "tournaments", tournamentId],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET("/api/v1/leagues/{league_id}/tournaments/{tournament_id}", {
            params: {
              path: { league_id: leagueId, tournament_id: tournamentId },
            },
            signal,
          }),
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
