// Helpers for the tests of the list and the setup steps.
import axe from "axe-core";

import { api, dataOf } from "@/api/client";
import type { components } from "@/api/schema";

import { DEMO_LEAGUE_ID, DEMO_SEASON_ID } from "./ids";
import { newId } from "./setupEngine";

type TournamentCreate = components["schemas"]["TournamentCreate"];

/** A DYP evening as screen 2 would create it; left-out settings take the defaults. */
export const dypFormat: Omit<TournamentCreate, "id"> = {
  name: "DYP on 22 October",
  date: "2026-10-22",
  type: "dyp",
  group_phase: "round_robin",
  round_robin_legs: 1,
  sit_out_points: null,
  group_match_format: "bo1",
  goals_per_game: 10,
  field_count: 2,
};

const league = { league_id: DEMO_LEAGUE_ID };
const at = (tournamentId: string) => ({
  params: { path: { ...league, tournament_id: tournamentId } },
});

/**
 * A tournament in setup, made through the API like screen 2 does. The
 * settings the chosen phases do not use are null.
 */
export async function createDraft(
  format: Partial<Omit<TournamentCreate, "id">> = {},
): Promise<string> {
  const id = newId();
  const groupPhase = format.group_phase ?? dypFormat.group_phase;
  const base = {
    ...dypFormat,
    round_robin_legs: groupPhase === "round_robin" ? 1 : null,
    // BR-071: only Swiss and Monster DYP take sit-out points, not a round robin.
    sit_out_points:
      groupPhase === "swiss" || groupPhase === "monster_dyp" ? 0 : null,
    group_match_format: groupPhase === "none" ? null : "bo1",
  } as const;
  await dataOf(
    api.POST("/api/v1/leagues/{league_id}/tournaments", {
      params: { path: league },
      body: { ...base, ...format, id },
    }),
  );
  return id;
}

/** The first `count` players of the league ranking, picked for the tournament. */
export async function pickPlayers(tournamentId: string, count: number) {
  const { ranking } = await setupOf(tournamentId);
  return dataOf(
    api.PUT(
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
    api.GET(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup",
      at(tournamentId),
    ),
  );
}

export function tournamentOf(tournamentId: string) {
  return dataOf(
    api.GET(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
      at(tournamentId),
    ),
  );
}

/**
 * axe on the rendered page. jsdom computes no layout or colours, so
 * colour-contrast cannot run here (the ratios of the tokens are checked from
 * a script, docs/style/frontend-style.md §5.2), and the page sits in no landmark.
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
    api.POST(
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

/** Another device swaps seeds 1 and 2; the draw counter does not change (ADR-010). */
export async function swapSeedsElsewhere(tournamentId: string) {
  const [first, second, ...rest] = startBody(
    await setupOf(tournamentId),
  ).expected_seed_order;
  await dataOf(
    api.PUT(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/seed-order",
      {
        ...at(tournamentId),
        body: { entry_ids: [second ?? "", first ?? "", ...rest] },
      },
    ),
  );
}

type StartWrite = components["schemas"]["StartWrite"];

/**
 * The body of the start as the review would send it: the setup's draw counter
 * (or the given one) and its entries in seed order (ADR-008).
 */
export function startBody(
  setup: Awaited<ReturnType<typeof setupOf>>,
  counter: number = setup.draw_counter,
): StartWrite {
  return {
    expected_draw_counter: counter,
    expected_seed_order: setup.entries
      .filter((entry) => entry.stage === "main")
      .toSorted((a, b) => (a.seed ?? 0) - (b.seed ?? 0))
      .map((entry) => entry.id),
  };
}

/** Generates and starts a tournament with its current draw counter and seeds. */
export async function startTournament(tournamentId: string) {
  await dataOf(
    api.POST("/api/v1/leagues/{league_id}/tournaments/{tournament_id}/start", {
      ...at(tournamentId),
      body: startBody(await setupOf(tournamentId)),
    }),
  );
}

export function tournamentsOfSeason() {
  return dataOf(
    api.GET("/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments", {
      params: { path: { ...league, season_id: DEMO_SEASON_ID } },
    }),
  );
}

/** The league allows draws (BR-121), so BO2 is offered. */
export async function allowDraws() {
  await dataOf(
    api.PATCH("/api/v1/leagues/{league_id}", {
      params: { path: league },
      body: { draws_allowed: true },
    }),
  );
}
