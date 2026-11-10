// Helpers for the tests of the list and the setup steps.
import axe from "axe-core";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

import type { TournamentFormatWrite } from "./contract";
import { DEMO_LEAGUE_ID, DEMO_SEASON_ID } from "./seed";
import { newId } from "./setupEngine";

/** The formats of a DYP evening as screen 2 would send them. */
export const dypFormat: TournamentFormatWrite = {
  name: "DYP on 22 October",
  date: "2026-10-22",
  type: "dyp",
  group_phase: "round_robin",
  round_robin_legs: 1,
  sit_out_points: 0,
  group_match_format: "bo1",
  knockout_match_format: "bo1",
  final_match_format: null,
  third_place_match: false,
  goals_per_game: 10,
  field_count: 2,
};

const league = { league_id: DEMO_LEAGUE_ID };
const at = (tournamentId: string) => ({
  params: { path: { ...league, tournament_id: tournamentId } },
});

/** A tournament in setup, made through the API like screen 2 does. */
export async function createDraft(
  format: Partial<TournamentFormatWrite> = {},
): Promise<string> {
  const id = newId();
  await dataOf(
    provisionalApi.POST("/api/v1/leagues/{league_id}/tournaments", {
      params: { path: league },
      body: { ...dypFormat, ...format, id },
    }),
  );
  return id;
}

/** The first `count` players of the league ranking, picked for the tournament. */
export async function pickPlayers(tournamentId: string, count: number) {
  const ranking = await dataOf(
    provisionalApi.GET("/api/v1/leagues/{league_id}/ranking", {
      params: { path: league },
    }),
  );
  return dataOf(
    provisionalApi.PUT(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/players",
      {
        ...at(tournamentId),
        body: { player_ids: ranking.slice(0, count).map((r) => r.player_id) },
      },
    ),
  );
}

export function setupOf(tournamentId: string) {
  return dataOf(
    provisionalApi.GET(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup",
      at(tournamentId),
    ),
  );
}

export function tournamentOf(tournamentId: string) {
  return dataOf(
    provisionalApi.GET(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
      at(tournamentId),
    ),
  );
}

/**
 * axe on the rendered page. jsdom computes no layout or colours, so
 * colour-contrast cannot run here (the ratios of the tokens are checked from
 * a script, docs/frontend-style.md §5.2), and the page sits in no landmark.
 */
export async function axeViolations(): Promise<string[]> {
  const results = await axe.run(document.body, {
    runOnly: [
      "wcag2a",
      "wcag2aa",
      "wcag21a",
      "wcag21aa",
      "wcag22aa",
      "best-practice",
    ],
    rules: {
      "color-contrast": { enabled: false },
      region: { enabled: false },
    },
  });
  return results.violations.map(
    (violation) =>
      `${violation.id}: ${violation.help} (${violation.nodes
        .map((node) => node.target.join(" "))
        .join("; ")})`,
  );
}

/** The item at `index`; fails the test when there is none. */
export function nth<T>(items: readonly T[], index: number): T {
  const item = items[index];
  if (item === undefined) {
    throw new Error(`No item at ${String(index)}`);
  }
  return item;
}

/** Another device draws with the counter it knows (a change this screen has not seen). */
export async function drawElsewhere(
  tournamentId: string,
  target: "pairs" | "seeds",
) {
  await dataOf(
    provisionalApi.POST(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/draw",
      {
        ...at(tournamentId),
        body: {
          expected_draw_counter: (await setupOf(tournamentId)).draw_counter,
          target,
        },
      },
    ),
  );
}

/** Generates and starts a tournament with its current draw counter. */
export async function startTournament(tournamentId: string) {
  await dataOf(
    provisionalApi.POST(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/start",
      {
        ...at(tournamentId),
        body: {
          expected_draw_counter: (await setupOf(tournamentId)).draw_counter,
        },
      },
    ),
  );
}

export function tournamentsOfSeason() {
  return dataOf(
    provisionalApi.GET(
      "/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments",
      { params: { path: { ...league, season_id: DEMO_SEASON_ID } } },
    ),
  );
}

/** The league allows draws (BR-121), so BO2 is offered. */
export async function allowDraws() {
  await dataOf(
    provisionalApi.PUT("/api/v1/leagues/{league_id}/settings", {
      params: { path: league },
      body: {
        name: "Thursday Foosball",
        draws_allowed: true,
        default_field_count: 2,
        default_match_format: "bo1",
        default_goals_per_game: 10,
        placement_points: [10, 8, 6, 4, 2],
      },
    }),
  );
}
