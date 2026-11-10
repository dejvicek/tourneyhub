import { describe, expect, it } from "vitest";

import { ApiError, dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

import { rules } from "./rules";
import { DEMO_LEAGUE_ID, demoId } from "./seed";

// Ids of the finals seed (seedFinals.ts).
const DYP_EVENING = demoId(3200);
const MONSTER = demoId(3300);
const SWISS = demoId(3450);
const SPRING_CUP = demoId(3600);
const GRAND_PRIX = demoId(3700);

const base = (tournamentId: string) => ({
  league_id: DEMO_LEAGUE_ID,
  tournament_id: tournamentId,
});
const root = "/api/v1/leagues/{league_id}/tournaments/{tournament_id}";

const bracket = (id: string) =>
  dataOf(provisionalApi.GET(`${root}/bracket`, { params: { path: base(id) } }));
const places = (id: string) =>
  dataOf(provisionalApi.GET(`${root}/places`, { params: { path: base(id) } }));

/** Enters a result for every match that can be played, until none is left. */
async function playOut(id: string): Promise<void> {
  for (let pass = 0; pass < 20; pass++) {
    const open = (await bracket(id)).rounds
      .flatMap((round) => round.matches)
      .filter((m) => m.state === "ready" || m.state === "on_field");
    if (open.length === 0) {
      return;
    }
    for (const match of open) {
      const games =
        match.match_format === "bo1"
          ? [{ winner: "side_1" as const, score_1: 10, score_2: 3 }]
          : [
              { winner: "side_1" as const, score_1: 10, score_2: 3 },
              { winner: "side_1" as const, score_1: 10, score_2: 4 },
            ];
      await dataOf(
        provisionalApi.PUT(`${root}/matches/{match_id}/result`, {
          params: { path: { ...base(id), match_id: match.match_id } },
          body: { walkover_winner: null, games },
        }),
      );
    }
  }
}

describe("the finals in the fake API", () => {
  it.each([
    [DYP_EVENING, 4, 0],
    [SPRING_CUP, 8, 2],
    [GRAND_PRIX, 16, 3],
  ])(
    "draws the bracket of %s with %i spots and %i byes (BR-040, BR-041)",
    async (id, size, byes) => {
      const result = await bracket(id);
      expect(result.size).toBe(size);
      expect(result.rounds).toHaveLength(Math.log2(size));
      const first = result.rounds[0]?.matches ?? [];
      expect(first).toHaveLength(size / 2);
      expect(first.filter((m) => m.state === "bye")).toHaveLength(byes);
      // BR-042: seeds 1 and 2 are on opposite halves.
      const seeds = first.flatMap((m) => m.sides.map((s) => s.seed));
      expect(seeds.indexOf(1)).toBeLessThan(first.length);
      expect(seeds.indexOf(2)).toBeGreaterThanOrEqual(first.length);
    },
  );

  it("gives the final its own format and a field (BR-120)", async () => {
    const result = await bracket(DYP_EVENING);
    const final = result.rounds.at(-1)?.matches[0];
    expect(final).toMatchObject({
      state: "on_field",
      match_format: "bo3",
      field_number: 1,
    });
    expect(result.rounds[0]?.matches[0]?.match_format).toBe("bo1");
  });

  it("shares places and rounds the split points down (BR-102, BR-104, BR-111)", async () => {
    await playOut(GRAND_PRIX);
    const result = await places(GRAND_PRIX);

    expect(result.complete).toBe(true);
    const byPlace = (place: number) =>
      result.rows.filter((row) => row.place === place);
    expect(result.rows).toHaveLength(13);
    expect(byPlace(1)).toHaveLength(1);
    expect(byPlace(2)).toHaveLength(1);
    // The two semifinal losers share 3rd: (6 + 4) / 2 = 5 each.
    expect(byPlace(3).map((r) => r.points_per_player)).toEqual([5, 5]);
    // Four quarterfinal losers share 5th: (2 + 0 + 0 + 0) / 4 = 0.5, down to 0.
    expect(byPlace(5)).toHaveLength(4);
    expect(byPlace(5).every((r) => r.points_per_player === 0)).toBe(true);
    // The numbering skips: no 4th, 6th, 7th or 8th (BR-104); round-of-16 losers share 9th.
    expect(byPlace(4)).toHaveLength(0);
    expect(byPlace(9)).toHaveLength(5);
  });

  it("adds a round only with the number the organizer expects (ADR-008)", async () => {
    const add = (expected: number) =>
      dataOf(
        provisionalApi.POST(`${root}/rounds`, {
          params: { path: base(SWISS) },
          body: { expected_round_no: expected },
        }),
      );

    const added = await add(4);
    expect(added.round_no).toBe(4);
    // A repeated request and a stale screen get 409.
    await expect(add(4)).rejects.toMatchObject({ status: 409 });
    await expect(add(2)).rejects.toMatchObject({ status: 409 });
    // Round 4 has no results yet, so there is no round 5 (FR-040).
    await expect(add(5)).rejects.toMatchObject({ status: 422 });
  });

  it("deletes only the newest round, by its id (BR-066)", async () => {
    const tournament = await dataOf(
      provisionalApi.GET(`${root}`, { params: { path: base(SWISS) } }),
    );
    const [first, , third] = tournament.rounds;
    const remove = (roundId: string) =>
      dataOf(
        provisionalApi.DELETE(`${root}/rounds/{round_id}`, {
          params: { path: { ...base(SWISS), round_id: roundId } },
        }),
      );

    await expect(remove(first?.id ?? "")).rejects.toMatchObject({
      status: 409,
    });
    await remove(third?.id ?? "");
    // Deleting it again means it is already gone.
    await expect(remove(third?.id ?? "")).rejects.toBeInstanceOf(ApiError);
    await expect(remove(third?.id ?? "")).rejects.toMatchObject({
      status: 404,
    });
  });

  it("disables and enables a player with the target state (BR-064)", async () => {
    const entries = await dataOf(
      provisionalApi.GET(`${root}/participants`, {
        params: { path: base(MONSTER) },
      }),
    );
    const playing = entries.find((e) => e.state === "playing");
    const set = (disabled: boolean) =>
      dataOf(
        provisionalApi.PUT(`${root}/entries/{entry_id}/disabled`, {
          params: {
            path: { ...base(MONSTER), entry_id: playing?.entry_id ?? "" },
          },
          body: { disabled },
        }),
      );

    expect(await set(true)).toMatchObject({
      state: "disabled",
      disabled_since_round: 6,
    });
    // Sending the same state again changes nothing.
    expect(await set(true)).toMatchObject({
      state: "disabled",
      disabled_since_round: 6,
    });
    expect(await set(false)).toMatchObject({
      state: "playing",
      disabled_since_round: null,
    });
  });

  it("warns nothing and starts a late player with 0 points from the next round (BR-067)", async () => {
    const players = await dataOf(
      provisionalApi.GET("/api/v1/leagues/{league_id}/players", {
        params: { path: { league_id: DEMO_LEAGUE_ID } },
      }),
    );
    const tournament = await dataOf(
      provisionalApi.GET(`${root}`, { params: { path: base(MONSTER) } }),
    );
    const outside = players.find(
      (p) => !tournament.entries.some((e) => e.player_ids.includes(p.id)),
    );
    const late = await dataOf(
      provisionalApi.POST(`${root}/entries`, {
        params: { path: base(MONSTER) },
        body: { player_id: outside?.id ?? "", from_round_no: 6 },
      }),
    );
    expect(late).toMatchObject({ joined_round: 6, state: "playing" });
    const ranking = await dataOf(
      provisionalApi.GET(`${root}/ranking`, {
        params: { path: base(MONSTER) },
      }),
    );
    expect(
      ranking.rows.find((r) => r.entry_id === late.entry_id),
    ).toMatchObject({
      points: 0,
      played: 0,
    });
  });

  describe.each(rules.monsterKnockoutModes)(
    "the Monster DYP knockout, %s",
    (mode) => {
      it("previews and draws it (FR-045, BR-081–BR-084)", async () => {
        const paired = mode !== "singles";
        const preview = await dataOf(
          provisionalApi.GET(`${root}/knockout/preview`, {
            params: {
              path: base(MONSTER),
              query: { qualifiers: 8, third_place_match: false, mode, draw: 0 },
            },
          }),
        );
        expect(preview.entries).toHaveLength(paired ? 4 : 8);
        expect(
          preview.entries.every((e) => e.members.length === (paired ? 2 : 1)),
        ).toBe(true);
        // BR-080: the disabled player does not go through; the next one moves up.
        expect(preview.skipped_entry_ids).toHaveLength(1);
        const going = preview.entries.flatMap((e) =>
          e.members.map((m) => m.entry_id),
        );
        expect(going).not.toContain(preview.skipped_entry_ids[0]);
        if (mode === "seeded_pairs") {
          // The best partners the (N/2 + 1)th of the qualifiers, and so on (BR-081).
          const ranking = await dataOf(
            provisionalApi.GET(`${root}/ranking`, {
              params: { path: base(MONSTER) },
            }),
          );
          const active = ranking.rows
            .filter((r) => !r.is_disabled)
            .map((r) => r.entry_id);
          expect(
            preview.entries.map((e) => e.members.map((m) => m.entry_id)),
          ).toEqual([
            [active[0], active[4]],
            [active[1], active[5]],
            [active[2], active[6]],
            [active[3], active[7]],
          ]);
        }

        const drawn = await dataOf(
          provisionalApi.PUT(`${root}/knockout`, {
            params: { path: base(MONSTER) },
            body: { qualifiers: 8, third_place_match: true, mode, draw: 0 },
          }),
        );
        expect(drawn.size).toBe(paired ? 4 : 8);
        expect(drawn.third_place_match).toBe(true);
        const tournament = await dataOf(
          provisionalApi.GET(`${root}`, { params: { path: base(MONSTER) } }),
        );
        expect(tournament.phases.at(-1)).toMatchObject({
          kind: "knockout",
          monster_knockout_mode: mode,
          third_place_match: true,
        });
      });
    },
  );

  it("deletes the knockout and unlocks the group phase (FR-046, BR-087)", async () => {
    const drawn = await dataOf(
      provisionalApi.PUT(`${root}/knockout`, {
        params: { path: base(MONSTER) },
        body: {
          qualifiers: 8,
          third_place_match: false,
          mode: "singles",
          draw: 0,
        },
      }),
    );
    await dataOf(
      provisionalApi.DELETE(`${root}/phases/{phase_id}`, {
        params: { path: { ...base(MONSTER), phase_id: drawn.phase_id } },
      }),
    );
    const tournament = await dataOf(
      provisionalApi.GET(`${root}`, { params: { path: base(MONSTER) } }),
    );
    expect(tournament.phases.some((p) => p.kind === "knockout")).toBe(false);
    expect(tournament.entries.some((e) => e.stage === "knockout")).toBe(false);
  });

  it("finishes a Swiss after confirming, and gives the places by the standings (FR-040)", async () => {
    const finished = await dataOf(
      provisionalApi.PUT(`${root}/state`, {
        params: { path: base(SWISS) },
        body: { state: "finished" },
      }),
    );
    expect(finished.state).toBe("finished");
    const result = await places(SWISS);
    expect(result.complete).toBe(true);
    expect(result.rows).toHaveLength(9);
    expect(result.rows[0]).toMatchObject({ place: 1, points_per_player: 10 });
  });
});
