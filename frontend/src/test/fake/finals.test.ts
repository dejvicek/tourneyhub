import { describe, expect, it } from "vitest";

import { api, ApiError, dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";
import { rules } from "@/lib/rules";

import {
  createDraft,
  pickPlayers,
  setupOf,
  startBody,
  tournamentOf,
} from "../setupTestHelpers";
import { TEST_LEAGUE_ID, testId } from "./ids";

// Ids of the finals seed (seedFinals.ts).
const DYP_EVENING = testId(3200);
const MONSTER = testId(3300);
const SWISS = testId(3450);
const SPRING_CUP = testId(3600);
const GRAND_PRIX = testId(3700);

const base = (tournamentId: string) => ({
  league_id: TEST_LEAGUE_ID,
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

/** A knockout start; the demo does not check the expected phase or qualifiers. */
const KNOCKOUT = {
  expected_current_phase_id: "",
  expected_qualifier_ids: [] as string[],
  qualifiers: 8,
  third_place_match: false,
  match_format: null,
  final_match_format: null,
} as const;

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

  it("adds a round only with the number the organizer expects (ADR-008, FR-040)", async () => {
    const add = (expected: number) =>
      dataOf(
        api.POST(`${root}/rounds`, {
          params: { path: base(SWISS) },
          body: { expected_round_no: expected },
        }),
      );

    const added = await add(4);
    expect(added.round_no).toBe(4);
    expect(added.is_sit_out_by_lot).toBe(false);
    // A repeated request and a stale screen get 409 with the newest round.
    await expect(add(4)).rejects.toMatchObject({
      status: 409,
      code: "round_number_changed",
      detail: { current_round_no: 4 },
    });
    await expect(add(2)).rejects.toMatchObject({
      status: 409,
      code: "round_number_changed",
    });
    // Round 4 has no results yet, so there is no round 5 (FR-040).
    await expect(add(5)).rejects.toMatchObject({
      status: 422,
      code: "round_not_complete",
    });
  });

  it("FR-032, BR-064: fake Monster DYP needs four players who are not disabled", async () => {
    const entries = await dataOf(
      provisionalApi.GET(`${root}/participants`, {
        params: { path: base(MONSTER) },
      }),
    );
    const playing = entries.filter((e) => e.state !== "disabled");
    for (const entry of playing.slice(3)) {
      await dataOf(
        provisionalApi.PUT(`${root}/entries/{entry_id}/disabled`, {
          params: { path: { ...base(MONSTER), entry_id: entry.entry_id } },
          body: { disabled: true },
        }),
      );
    }
    const tournament = await dataOf(
      provisionalApi.GET(root, { params: { path: base(MONSTER) } }),
    );

    await expect(
      dataOf(
        api.POST(`${root}/rounds`, {
          params: { path: base(MONSTER) },
          body: { expected_round_no: tournament.rounds.length + 1 },
        }),
      ),
    ).rejects.toMatchObject({
      status: 422,
      code: "not_enough_players",
      detail: { minimum: 4, given: 3 },
    });
  });

  describe("the second Monster DYP round's top players (BR-061)", () => {
    /** Starts a Monster DYP of the first `count` players with the given ranks marked. */
    async function startMonster(count: number, marked: number[], keep = count) {
      const id = await createDraft({
        type: "monster_dyp",
        group_phase: "monster_dyp",
      });
      const picked = (await pickPlayers(id, count)).ranking
        .slice(0, count)
        .map((row) => row.player_id);
      const marks = marked.map((rank) => picked[rank] ?? "");
      await dataOf(
        api.PUT(`${root}/setup/top-players`, {
          params: { path: base(id) },
          body: { player_ids: marks },
        }),
      );
      // Fewer players than marks allow (FR-041): the marks stay with the ones kept.
      if (keep < count) {
        await dataOf(
          api.PUT(`${root}/setup/players`, {
            params: { path: base(id) },
            body: { player_ids: picked.slice(0, keep) },
          }),
        );
      }
      await dataOf(
        api.POST(`${root}/start`, {
          params: { path: base(id) },
          body: startBody(await setupOf(id)),
        }),
      );
      return { id, marks, picked };
    }

    /** Plays round 1, adds round 2 and gives the players of each of its matches. */
    async function secondRound(id: string) {
      const first = (await tournamentOf(id)).rounds[0];
      for (const match of first?.matches ?? []) {
        await dataOf(
          provisionalApi.PUT(`${root}/matches/{match_id}/result`, {
            params: { path: { ...base(id), match_id: match.id } },
            body: {
              walkover_winner: null,
              games: [{ winner: "side_1", score_1: 10, score_2: 3 }],
            },
          }),
        );
      }
      const second = await dataOf(
        api.POST(`${root}/rounds`, {
          params: { path: base(id) },
          body: { expected_round_no: 2 },
        }),
      );
      return second.matches.map((match) =>
        match.sides.flatMap((side) => side.player_ids),
      );
    }

    it("BR-061: fake marked players lead different groups", async () => {
      const { id, marks } = await startMonster(9, [7, 8]);

      const groups = await secondRound(id);

      expect(groups).toHaveLength(2);
      // One of the 9 sits out. A marked player who plays leads a group of his
      // own (the first player of a group is its top player); one who sits out
      // is replaced by the next in the league order (BR-063).
      const leaders = groups.map((group) => group[0]);
      const playing = marks.filter((mark) => groups.flat().includes(mark));
      expect(playing.length).toBeGreaterThan(0);
      for (const mark of playing) {
        expect(leaders).toContain(mark);
      }
      expect(new Set(leaders).size).toBe(2);
    });

    it("BR-061: fake surplus marks at start", async () => {
      // Two marks, but 7 players make one match: only the first marked one leads.
      const { id, marks } = await startMonster(9, [5, 6], 7);

      const groups = await secondRound(id);

      expect(groups).toHaveLength(1);
      // The leader is the first marked player who plays in that round.
      const firstPlaying = marks.find((mark) => groups.flat().includes(mark));
      expect(firstPlaying).toBeDefined();
      expect(groups[0]?.[0]).toBe(firstPlaying);
    });

    it("BR-061: fake an unmarked top player is the best by league ranking, not by standing", async () => {
      // One mark: the second group is led by the best-ranked player in the
      // league among those who play, not by the best in the standings.
      const { id, marks, picked } = await startMonster(9, [7]);

      const groups = await secondRound(id);

      const playing = groups.flat();
      const bestInLeague = picked.find(
        (player) => !marks.includes(player) && playing.includes(player),
      );
      expect(bestInLeague).toBeDefined();
      expect(groups.map((group) => group[0])).toEqual([marks[0], bestInLeague]);
    });
  });

  it("deletes only the newest round, by its id (BR-066)", async () => {
    const tournament = await dataOf(
      provisionalApi.GET(root, { params: { path: base(SWISS) } }),
    );
    const [first, , third] = tournament.rounds;
    const remove = (roundId: string) =>
      dataOf(
        api.DELETE(`${root}/rounds/{round_id}`, {
          params: { path: { ...base(SWISS), round_id: roundId } },
        }),
      );

    await expect(remove(first?.id ?? "")).rejects.toMatchObject({
      status: 409,
      code: "round_not_newest",
      detail: { round_id: third?.id },
    });
    await remove(third?.id ?? "");
    // Deleting it again means it is already gone.
    await expect(remove(third?.id ?? "")).rejects.toBeInstanceOf(ApiError);
    await expect(remove(third?.id ?? "")).rejects.toMatchObject({
      status: 404,
      code: "round_not_found",
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
        params: { path: { league_id: TEST_LEAGUE_ID } },
      }),
    );
    const tournament = await dataOf(
      provisionalApi.GET(root, { params: { path: base(MONSTER) } }),
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
    const play = await dataOf(
      api.GET(`${root}/play`, { params: { path: base(MONSTER) } }),
    );
    expect(
      play.standings.find((r) => r.entry_id === late.entry_id),
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
              query: { qualifiers: 8, third_place_match: false, mode },
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
          const [play, tournament] = await Promise.all([
            dataOf(
              api.GET(`${root}/play`, { params: { path: base(MONSTER) } }),
            ),
            dataOf(api.GET(root, { params: { path: base(MONSTER) } })),
          ]);
          const disabled = new Set(
            tournament.entries.filter((e) => e.is_disabled).map((e) => e.id),
          );
          const active = play.standings
            .filter((r) => !disabled.has(r.entry_id))
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

        await dataOf(
          provisionalApi.PUT(`${root}/knockout`, {
            params: { path: base(MONSTER) },
            body: { ...KNOCKOUT, third_place_match: true, mode },
          }),
        );
        const drawn = await dataOf(
          provisionalApi.GET(`${root}/bracket`, {
            params: { path: base(MONSTER) },
          }),
        );
        expect(drawn.size).toBe(paired ? 4 : 8);
        expect(drawn.third_place_match).toBe(true);
        const tournament = await dataOf(
          provisionalApi.GET(root, { params: { path: base(MONSTER) } }),
        );
        expect(tournament.phases.at(-1)).toMatchObject({
          kind: "knockout",
          monster_knockout_mode: mode,
          third_place_match: true,
        });
      });
    },
  );

  it("refuses Lord have mercy until its re-mix is built (issue #63)", async () => {
    await expect(
      dataOf(
        provisionalApi.PUT(`${root}/knockout`, {
          params: { path: base(MONSTER) },
          body: { ...KNOCKOUT, mode: "lord_have_mercy" },
        }),
      ),
    ).rejects.toMatchObject({ status: 422 });
  });

  it("deletes the knockout and unlocks the group phase (FR-046, BR-087)", async () => {
    const drawn = await dataOf(
      provisionalApi.PUT(`${root}/knockout`, {
        params: { path: base(MONSTER) },
        body: { ...KNOCKOUT, mode: "singles" },
      }),
    );
    const phaseId = drawn.phases.find((p) => p.kind === "knockout")?.id ?? "";
    await dataOf(
      provisionalApi.DELETE(`${root}/phases/{phase_id}`, {
        params: { path: { ...base(MONSTER), phase_id: phaseId } },
      }),
    );
    const tournament = await dataOf(
      provisionalApi.GET(root, { params: { path: base(MONSTER) } }),
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
