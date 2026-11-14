import { describe, expect, it } from "vitest";

import { api, ApiError, dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";
import { rules } from "@/lib/rules";

import {
  createDraft,
  pickPlayers,
  setupOf,
  startBody,
  startTournament,
  tournamentOf,
} from "../setupTestHelpers";
import { TEST_LEAGUE_ID, TEST_SHARE_TOKEN, testId } from "./ids";
import { db } from "./store";

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
  expected_draw_counter: 0,
  expected_qualifier_ids: [] as string[],
  qualifiers: 8,
  third_place_match: false,
  match_format: null,
  final_match_format: null,
} as const;

describe("the finals in the fake API", () => {
  it("counts the knockout draws and refuses a stale one with 409 (ADR-008, FR-045)", async () => {
    const draw = (expected: number) =>
      dataOf(
        api.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout/draw",
          {
            params: { path: base(MONSTER) },
            body: { expected_draw_counter: expected },
          },
        ),
      );
    expect(await draw(0)).toEqual({ draw_counter: 1 });
    await expect(draw(0)).rejects.toMatchObject({
      status: 409,
      code: "draw_counter_changed",
    });
    expect(await draw(1)).toEqual({ draw_counter: 2 });
    const stale = api.PUT(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout",
      {
        params: { path: base(MONSTER) },
        body: { ...KNOCKOUT, mode: "singles", expected_draw_counter: 0 },
      },
    );
    await expect(dataOf(stale)).rejects.toMatchObject({
      status: 409,
      code: "draw_counter_changed",
    });
  });

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
      api.GET(`${root}/participants`, {
        params: { path: base(MONSTER) },
      }),
    );
    const playing = entries.filter((e) => e.state !== "disabled");
    for (const entry of playing.slice(3)) {
      await dataOf(
        api.PUT(`${root}/entries/{entry_id}/disabled`, {
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

      // The mark may sit out by lot (top players are not exempt, BR-061/BR-063),
      // so the expected leaders come from the players who actually play: the
      // mark if that player plays, then the best by league ranking among the others.
      const playing = groups.flat();
      const markPlays = marks.some((mark) => playing.includes(mark));
      const unmarkedPlaying = picked.filter(
        (player) => !marks.includes(player) && playing.includes(player),
      );
      const expected = markPlays
        ? [marks[0], unmarkedPlaying[0]]
        : unmarkedPlaying.slice(0, 2);
      // Either way at least one leader is an unmarked top player.
      expect(unmarkedPlaying.length).toBeGreaterThan(1);
      const leaders = groups.map((group) => group[0]);
      expect(leaders).toHaveLength(2);
      expect(leaders).toEqual(expect.arrayContaining(expected));
      if (markPlays) {
        expect(leaders).toEqual([marks[0], unmarkedPlaying[0]]);
      }
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
      api.GET(`${root}/participants`, {
        params: { path: base(MONSTER) },
      }),
    );
    const playing = entries.find((e) => e.state === "playing");
    const set = (disabled: boolean) =>
      dataOf(
        api.PUT(`${root}/entries/{entry_id}/disabled`, {
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

  describe("refuses disabling like the backend (BR-064)", () => {
    const disable = (id: string, entryId: string) =>
      dataOf(
        api.PUT(`${root}/entries/{entry_id}/disabled`, {
          params: { path: { ...base(id), entry_id: entryId } },
          body: { disabled: true },
        }),
      );
    const firstEntry = async (id: string) =>
      (
        await dataOf(
          api.GET(`${root}/participants`, { params: { path: base(id) } }),
        )
      )[0]?.entry_id ?? "";

    it("answers 404 entry_not_found for an unknown or a non-main entry", async () => {
      await expect(disable(MONSTER, testId(999_999))).rejects.toMatchObject({
        status: 404,
        code: "entry_not_found",
      });
      await dataOf(
        provisionalApi.PUT(`${root}/knockout`, {
          params: { path: base(MONSTER) },
          body: { ...KNOCKOUT, mode: "singles" },
        }),
      );
      const tournament = await dataOf(
        provisionalApi.GET(root, { params: { path: base(MONSTER) } }),
      );
      const knockoutEntry = tournament.entries.find(
        (e) => e.stage === "knockout",
      );
      await expect(
        disable(MONSTER, knockoutEntry?.id ?? ""),
      ).rejects.toMatchObject({ status: 404, code: "entry_not_found" });
    });

    it("answers 409 tournament_not_in_progress once the tournament is finished", async () => {
      const entryId = await firstEntry(SWISS);
      await dataOf(
        api.POST(`${root}/finish`, {
          params: { path: base(SWISS) },
          body: { expected_state: "in_progress" },
        }),
      );
      await expect(disable(SWISS, entryId)).rejects.toMatchObject({
        status: 409,
        code: "tournament_not_in_progress",
      });
    });

    it("answers 422 disable_not_allowed for a round robin and for a Monster DYP knockout other than Lord have mercy", async () => {
      await expect(
        disable(DYP_EVENING, await firstEntry(DYP_EVENING)),
      ).rejects.toMatchObject({ status: 422, code: "disable_not_allowed" });
      const entryId = await firstEntry(MONSTER);
      await dataOf(
        provisionalApi.PUT(`${root}/knockout`, {
          params: { path: base(MONSTER) },
          body: { ...KNOCKOUT, mode: "singles" },
        }),
      );
      await expect(disable(MONSTER, entryId)).rejects.toMatchObject({
        status: 422,
        code: "disable_not_allowed",
      });
    });

    it("answers 422 disable_not_allowed, not 404, for a knockout-only tournament", async () => {
      const id = await createDraft({ type: "singles", group_phase: "none" });
      await pickPlayers(id, 6);
      await startTournament(id);
      const entryId = await firstEntry(id);

      await expect(disable(id, entryId)).rejects.toMatchObject({
        status: 422,
        code: "disable_not_allowed",
      });
    });

    it("allows it during the Lord have mercy knockout", async () => {
      const entryId = await firstEntry(MONSTER);
      await dataOf(
        provisionalApi.PUT(`${root}/knockout`, {
          params: { path: base(MONSTER) },
          body: {
            ...KNOCKOUT,
            third_place_match: true,
            mode: "lord_have_mercy",
          },
        }),
      );
      expect(await disable(MONSTER, entryId)).toMatchObject({
        entry_id: entryId,
        state: "disabled",
      });
    });
  });

  describe("adds a late player like the backend (FR-047, BR-067)", () => {
    const outsider = async (id: string) => {
      const players = await dataOf(
        api.GET("/api/v1/leagues/{league_id}/players", {
          params: { path: { league_id: TEST_LEAGUE_ID } },
        }),
      );
      const tournament = await dataOf(
        api.GET(root, { params: { path: base(id) } }),
      );
      return {
        tournament,
        playerId:
          players.find(
            (p) => !tournament.entries.some((e) => e.player_ids.includes(p.id)),
          )?.id ?? "",
      };
    };
    const add = (id: string, playerId: string, fromRound: number) =>
      dataOf(
        api.POST(`${root}/entries`, {
          params: { path: base(id) },
          body: { player_id: playerId, from_round_no: fromRound },
        }),
      );
    const nextRound = (t: { rounds: unknown[] }) => t.rounds.length + 1;

    it("warns nothing and starts a late player with 0 points from the next round", async () => {
      const { playerId } = await outsider(MONSTER);
      const late = await add(MONSTER, playerId, 6);
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
      const tournament = await dataOf(
        api.GET(root, { params: { path: base(MONSTER) } }),
      );
      // A Monster DYP seeds nobody.
      expect(
        tournament.entries.find((e) => e.id === late.entry_id)?.seed,
      ).toBeNull();
    });

    it("gives a late player in a Singles Swiss the next seed", async () => {
      const { tournament, playerId } = await outsider(SWISS);
      const late = await add(SWISS, playerId, nextRound(tournament));
      const after = await dataOf(
        api.GET(root, { params: { path: base(SWISS) } }),
      );
      const seeds = tournament.entries.map((e) => e.seed ?? 0);
      expect(after.entries.find((e) => e.id === late.entry_id)?.seed).toBe(
        Math.max(...seeds) + 1,
      );
    });

    it("answers 404 player_not_found for a player of no league", async () => {
      await expect(add(MONSTER, testId(999_999), 6)).rejects.toMatchObject({
        status: 404,
        code: "player_not_found",
      });
    });

    it("answers 409 player_removed for a removed player", async () => {
      const { playerId } = await outsider(MONSTER);
      const player = db().players.find((p) => p.id === playerId);
      if (player) {
        player.removed_at = "2026-11-01T10:00:00Z";
      }
      await expect(add(MONSTER, playerId, 6)).rejects.toMatchObject({
        status: 409,
        code: "player_removed",
      });
    });

    it("answers 409 season_closed once the season is closed", async () => {
      const { playerId } = await outsider(MONSTER);
      for (const season of db().seasons) {
        season.state = "closed";
      }
      await expect(add(MONSTER, playerId, 6)).rejects.toMatchObject({
        status: 409,
        code: "season_closed",
      });
    });

    it("answers 409 tournament_not_in_progress once the tournament is finished", async () => {
      const { playerId } = await outsider(SWISS);
      await dataOf(
        api.POST(`${root}/finish`, {
          params: { path: base(SWISS) },
          body: { expected_state: "in_progress" },
        }),
      );
      await expect(add(SWISS, playerId, 4)).rejects.toMatchObject({
        status: 409,
        code: "tournament_not_in_progress",
      });
    });

    it("answers 422 format_not_supported for a round robin", async () => {
      const { playerId } = await outsider(DYP_EVENING);
      await expect(add(DYP_EVENING, playerId, 1)).rejects.toMatchObject({
        status: 422,
        code: "format_not_supported",
      });
    });

    it("answers 422 group_phase_locked once the knockout has started", async () => {
      const { playerId } = await outsider(SWISS);
      const swiss = db().tournaments.find((t) => t.id === SWISS);
      const group = swiss?.phases.find((p) => p.kind === "group");
      if (swiss && group) {
        swiss.phases.push({
          ...group,
          id: testId(999_001),
          kind: "knockout",
          format: "single_elimination",
        });
      }
      await expect(add(SWISS, playerId, 4)).rejects.toMatchObject({
        status: 422,
        code: "group_phase_locked",
      });
    });

    it("answers 422 late_entry_not_allowed in a DYP or Doubles Swiss", async () => {
      const { playerId } = await outsider(SWISS);
      const swiss = db().tournaments.find((t) => t.id === SWISS);
      for (const type of ["dyp", "doubles"] as const) {
        if (swiss) {
          swiss.type = type;
        }
        await expect(add(SWISS, playerId, 4)).rejects.toMatchObject({
          status: 422,
          code: "late_entry_not_allowed",
          detail: { type },
        });
      }
    });

    it("answers 422 player_already_in_tournament for a player who plays", async () => {
      const tournament = await dataOf(
        api.GET(root, { params: { path: base(MONSTER) } }),
      );
      await expect(
        add(MONSTER, tournament.entries[0]?.player_ids[0] ?? "", 6),
      ).rejects.toMatchObject({
        status: 422,
        code: "player_already_in_tournament",
      });
    });

    it("answers 409 round_number_changed with the current round number", async () => {
      const { playerId } = await outsider(MONSTER);
      await expect(add(MONSTER, playerId, 5)).rejects.toMatchObject({
        status: 409,
        code: "round_number_changed",
        detail: { current_round_no: 5 },
      });
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
        // BR-155: a Lord have mercy knockout has no bracket, only its rounds.
        const drawn =
          mode === "lord_have_mercy"
            ? await dataOf(
                api.GET(`${root}/knockout/rounds`, {
                  params: { path: base(MONSTER) },
                }),
              )
            : await bracket(MONSTER);
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
      api.POST(`${root}/finish`, {
        params: { path: base(SWISS) },
        body: { expected_state: "in_progress" },
      }),
    );
    expect(finished.state).toBe("finished");
    const result = await places(SWISS);
    expect(result.complete).toBe(true);
    expect(result.rows).toHaveLength(9);
    expect(result.rows[0]).toMatchObject({ place: 1, points_per_player: 10 });
  });
});

describe("the Lord have mercy knockout in the fake API", () => {
  const remixRoot = `${root}/knockout/rounds` as const;
  const remixBase = base(MONSTER);

  /** BR-084: 8 qualifiers make 4 pairs, so 2 semifinals, then the final and the third-place match. */
  const startRemix = () =>
    dataOf(
      provisionalApi.PUT(`${root}/knockout`, {
        params: { path: remixBase },
        body: {
          ...KNOCKOUT,
          third_place_match: true,
          mode: "lord_have_mercy",
        },
      }),
    );
  const readRounds = () =>
    dataOf(api.GET(remixRoot, { params: { path: remixBase } }));
  const drawRound = (expected: number) =>
    dataOf(
      api.POST(remixRoot, {
        params: { path: remixBase },
        body: { expected_round_no: expected },
      }),
    );
  const resultPath = (matchId: string) => ({
    ...remixBase,
    match_id: matchId,
  });
  const enter = (
    matchId: string,
    winner: "side_1" | "side_2" = "side_1",
    score = 10,
  ) =>
    dataOf(
      provisionalApi.PUT(`${root}/matches/{match_id}/result`, {
        params: { path: resultPath(matchId) },
        body: {
          walkover_winner: null,
          games: [
            winner === "side_1"
              ? { winner, score_1: score, score_2: 3 }
              : { winner, score_1: 3, score_2: score },
          ],
        },
      }),
    );
  const clear = (matchId: string) =>
    dataOf(
      provisionalApi.PUT(`${root}/matches/{match_id}/result`, {
        params: { path: resultPath(matchId) },
        body: { walkover_winner: null, games: [] },
      }),
    );
  /** Plays every match of the newest round, side 1 winning. */
  async function playNewest(): Promise<void> {
    const read = await readRounds();
    for (const match of read.rounds.at(-1)?.matches ?? []) {
      await enter(match.match_id);
    }
  }

  it("starts a Lord have mercy knockout with round 1 only (BR-140)", async () => {
    const tournament = await startRemix();
    const knockout = tournament.phases.find((p) => p.kind === "knockout");
    expect(knockout?.monster_knockout_mode).toBe("lord_have_mercy");
    const read = await readRounds();
    expect(read).toMatchObject({
      size: 4,
      round_count: 2,
      third_place_match: true,
      can_draw_next: false,
      left_player_ids: [],
    });
    expect(read.rounds).toHaveLength(1);
    const [first] = read.rounds;
    expect(first).toMatchObject({
      round_no: 1,
      name: "semifinal",
      result_count: 0,
    });
    expect(first?.matches).toHaveLength(2);
    for (const match of first?.matches ?? []) {
      expect(match.sides.map((s) => s.player_ids.length)).toEqual([2, 2]);
      expect(match).toMatchObject({ kind: "standard", winner_locked: false });
    }
    // BR-140: the other rounds do not exist yet.
    expect(
      tournament.rounds.filter((r) => r.phase_id === knockout?.id),
    ).toHaveLength(1);
  });

  it("refuses the next round until round 1 is complete (BR-140)", async () => {
    await startRemix();
    const [one, two] = (await readRounds()).rounds[0]?.matches ?? [];
    await expect(drawRound(2)).rejects.toMatchObject({
      status: 422,
      code: "round_not_complete",
      detail: { matches_left: 2 },
    });
    await enter(one?.match_id ?? "");
    await expect(drawRound(2)).rejects.toMatchObject({
      detail: { matches_left: 1 },
    });
    expect((await readRounds()).can_draw_next).toBe(false);
    await enter(two?.match_id ?? "");
    const ready = await readRounds();
    expect(ready.can_draw_next).toBe(true);
    const drawn = await drawRound(2);
    expect(drawn.rounds).toHaveLength(2);
    expect(drawn.can_draw_next).toBe(false);
    // BR-141, BR-144: the final's round has the final and the third-place match.
    const finalRound = drawn.rounds[1];
    expect(finalRound).toMatchObject({ round_no: 2, name: "final" });
    expect(finalRound?.matches.map((m) => m.kind)).toEqual([
      "standard",
      "third_place",
    ]);
    // BR-141: the winners are mixed into new pairs.
    const winners = (drawn.rounds[0]?.matches ?? []).flatMap((m) =>
      m.sides.slice(0, 1).flatMap((s) => s.player_ids),
    );
    const inFinal = finalRound?.matches[0]?.sides.flatMap((s) => s.player_ids);
    expect([...(inFinal ?? [])].sort()).toEqual([...winners].sort());
  });

  it("refuses a stale expected_round_no with 409 round_number_changed", async () => {
    await startRemix();
    for (const expected of [1, 3]) {
      await expect(drawRound(expected)).rejects.toMatchObject({
        status: 409,
        code: "round_number_changed",
        detail: { current_round_no: 1 },
      });
    }
  });

  it("locks the winners of the round before and refuses a flipped winner with round_locked (BR-146)", async () => {
    await startRemix();
    await playNewest();
    const drawn = await drawRound(2);
    const locked = drawn.rounds[0]?.matches ?? [];
    expect(locked.every((m) => m.winner_locked)).toBe(true);
    expect(drawn.rounds[1]?.matches.every((m) => !m.winner_locked)).toBe(true);
    const first = locked[0]?.match_id ?? "";
    await expect(enter(first, "side_2")).rejects.toMatchObject({
      status: 422,
      code: "round_locked",
      detail: { round_no: 2 },
    });
    await expect(clear(first)).rejects.toMatchObject({
      status: 422,
      code: "round_locked",
      detail: { round_no: 2 },
    });
    // The newest round can be changed and cleared.
    const final = drawn.rounds[1]?.matches[0]?.match_id ?? "";
    await enter(final);
    await clear(final);
  });

  it("allows a corrected score with the same winner (BR-146)", async () => {
    await startRemix();
    await playNewest();
    const drawn = await drawRound(2);
    const first = drawn.rounds[0]?.matches[0]?.match_id ?? "";
    await enter(first, "side_1", 7);
    const read = await readRounds();
    expect(read.rounds[0]?.matches[0]).toMatchObject({
      outcome: "side_1",
      score: [7, 3],
      winner_locked: true,
    });
  });

  it("deletes only the newest round; round 1 deletes the knockout (FR-046, BR-087)", async () => {
    await startRemix();
    await playNewest();
    const drawn = await drawRound(2);
    const [one, two] = drawn.rounds;
    const remove = (roundId: string) =>
      dataOf(
        api.DELETE(`${remixRoot}/{round_id}`, {
          params: { path: { ...remixBase, round_id: roundId } },
        }),
      );
    await expect(remove(one?.round_id ?? "")).rejects.toMatchObject({
      status: 409,
      code: "round_not_newest",
      detail: { round_id: two?.round_id },
    });
    await expect(remove(testId(999_999))).rejects.toMatchObject({
      status: 404,
      code: "round_not_found",
    });
    await remove(two?.round_id ?? "");
    const after = await readRounds();
    expect(after.rounds).toHaveLength(1);
    // BR-146: the round before is unlocked again.
    expect(after.rounds[0]?.matches.every((m) => !m.winner_locked)).toBe(true);
    expect(after.can_draw_next).toBe(true);
    await remove(one?.round_id ?? "");
    await expect(readRounds()).rejects.toMatchObject({
      status: 404,
      code: "knockout_not_found",
    });
    const tournament = await dataOf(
      provisionalApi.GET(root, { params: { path: remixBase } }),
    );
    expect(tournament.phases.some((p) => p.kind === "knockout")).toBe(false);
    expect(tournament.state).toBe("in_progress");
  });

  it("finishes after the final and the third-place match (FR-037)", async () => {
    await startRemix();
    await playNewest();
    const drawn = await drawRound(2);
    const [final, third] = drawn.rounds[1]?.matches ?? [];
    const state = async () =>
      (await dataOf(provisionalApi.GET(root, { params: { path: remixBase } })))
        .state;
    await enter(final?.match_id ?? "");
    expect(await state()).toBe("in_progress");
    await enter(third?.match_id ?? "");
    expect(await state()).toBe("finished");
    // Clearing a result, or deleting the round, reopens it (BR-095).
    await clear(third?.match_id ?? "");
    expect(await state()).toBe("in_progress");
    await enter(third?.match_id ?? "");
    expect(await state()).toBe("finished");
    await dataOf(
      api.DELETE(`${remixRoot}/{round_id}`, {
        params: {
          path: { ...remixBase, round_id: drawn.rounds[1]?.round_id ?? "" },
        },
      }),
    );
    expect(await state()).toBe("in_progress");
  });

  it("gives places per player with the partner (BR-145)", async () => {
    await startRemix();
    await playNewest();
    const drawn = await drawRound(2);
    expect((await places(MONSTER)).rows).toEqual([]);
    for (const match of drawn.rounds[1]?.matches ?? []) {
      await enter(match.match_id);
    }
    const result = await places(MONSTER);
    expect(result.complete).toBe(true);
    const tournament = await dataOf(
      provisionalApi.GET(root, { params: { path: remixBase } }),
    );
    const main = tournament.entries.filter((e) => e.stage === "main");
    // One row per player, not per pair.
    expect(result.rows).toHaveLength(main.length);
    const knockout = result.rows.filter((r) => r.reason.kind !== "group_place");
    expect(knockout.map((r) => r.place)).toEqual([1, 1, 2, 2, 3, 3, 4, 4]);
    expect(knockout.map((r) => r.reason.kind)).toEqual([
      "won_final",
      "won_final",
      "lost_final",
      "lost_final",
      "won_third_place",
      "won_third_place",
      "lost_third_place",
      "lost_third_place",
    ]);
    const byEntry = new Map(result.rows.map((r) => [r.entry_id, r]));
    for (const row of knockout) {
      expect(row.reason.opponent_entry_id).toBeNull();
      const partner = byEntry.get(row.reason.partner_entry_id ?? "");
      expect(partner?.place).toBe(row.place);
      expect(partner?.reason.partner_entry_id).toBe(row.entry_id);
    }
    // BR-103: the others follow, each counting as one, with no partner.
    const rest = result.rows.filter((r) => r.reason.kind === "group_place");
    expect(rest.length).toBeGreaterThan(0);
    expect(rest.every((r) => r.reason.partner_entry_id === null)).toBe(true);
    expect(Math.min(...rest.map((r) => r.place))).toBe(5);
  });

  it("answers 422 format_not_supported on the bracket", async () => {
    await startRemix();
    const expected = {
      status: 422,
      code: "format_not_supported",
      detail: { format: "single_elimination", mode: "lord_have_mercy" },
    };
    await expect(bracket(MONSTER)).rejects.toMatchObject(expected);
    await expect(
      dataOf(
        provisionalApi.GET(
          "/api/v1/public/{share_token}/tournaments/{tournament_id}/bracket",
          {
            params: {
              path: {
                share_token: TEST_SHARE_TOKEN,
                tournament_id: MONSTER,
              },
            },
          },
        ),
      ),
    ).rejects.toMatchObject(expected);
  });

  it("answers the rounds read of a fixed-pair or missing knockout with a refusal", async () => {
    await expect(readRounds()).rejects.toMatchObject({
      status: 404,
      code: "knockout_not_found",
    });
    await dataOf(
      provisionalApi.PUT(`${root}/knockout`, {
        params: { path: remixBase },
        body: { ...KNOCKOUT, mode: "seeded_pairs" },
      }),
    );
    await expect(readRounds()).rejects.toMatchObject({
      status: 422,
      code: "format_not_supported",
      detail: { format: "single_elimination", mode: "seeded_pairs" },
    });
  });

  it("serves the share link a read without the organizer's fields (FR-070)", async () => {
    await startRemix();
    const read = await dataOf(
      api.GET(
        "/api/v1/public/{share_token}/tournaments/{tournament_id}/knockout/rounds",
        {
          params: {
            path: { share_token: TEST_SHARE_TOKEN, tournament_id: MONSTER },
          },
        },
      ),
    );
    expect(read.rounds).toHaveLength(1);
    expect(read).not.toHaveProperty("can_draw_next");
    expect(read.rounds[0]).not.toHaveProperty("result_count");
    expect(read.rounds[0]?.matches[0]).not.toHaveProperty("winner_locked");
  });
});
