import { describe, expect, it } from "vitest";

import { api, ApiError, dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

import { DEMO_LEAGUE_ID, DEMO_SEASON_ID } from "./ids";
import {
  createDraft,
  dypFormat,
  nth,
  pickPlayers,
  setupOf,
  tournamentOf,
} from "./setupTestHelpers";

const league = { league_id: DEMO_LEAGUE_ID };
const at = (tournament_id: string) => ({
  params: { path: { ...league, tournament_id } },
});

async function failure(call: Promise<unknown>) {
  try {
    await call;
  } catch (error) {
    if (error instanceof ApiError) {
      return error;
    }
    throw error;
  }
  throw new Error("The call did not fail");
}

describe("the fake API for tournament setup", () => {
  it("creates a tournament with the client's id, once", async () => {
    const id = await createDraft({ name: "Friday DYP" });
    const again = await dataOf(
      api.POST("/api/v1/leagues/{league_id}/tournaments", {
        params: { path: league },
        body: { ...dypFormat, id, name: "Friday DYP" },
      }),
    );
    const list = await dataOf(
      api.GET("/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments", {
        params: { path: { ...league, season_id: DEMO_SEASON_ID } },
      }),
    );

    expect(again.tournament_id).toBe(id);
    expect(list.filter((t) => t.id === id)).toHaveLength(1);
    expect(again.state).toBe("setup");
    expect(again.format.field_count).toBe(2);
  });

  it("refuses BO2 in a league without draws and a group phase the type does not allow", async () => {
    const bo2 = await failure(createDraft({ group_match_format: "bo2" }));
    const monster = await failure(createDraft({ type: "monster_dyp" }));

    expect([bo2.status, bo2.code]).toEqual([422, "draws_not_allowed"]);
    expect([monster.status, monster.code]).toEqual([422, "validation_failed"]);
    expect(monster.detail.errors).toEqual([
      { loc: ["body"], type: "group_phase_mismatch" },
    ]);
  });

  it("splits 13 players into halves, leaves one out by lot and draws 6 pairs", async () => {
    const id = await createDraft();
    const setup = await pickPlayers(id, 13);
    const read = await tournamentOf(id);

    expect(setup.halves.filter((h) => h.half === "left_out")).toHaveLength(1);
    expect(setup.halves.filter((h) => h.half === "top")).toHaveLength(6);
    expect(read.entries.map((entry) => entry.seed)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(read.entries.every((entry) => entry.player_ids.length === 2)).toBe(
      true,
    );
  });

  it("answers 409 to a draw with a stale counter and draws with the right one", async () => {
    const id = await createDraft();
    const before = await pickPlayers(id, 12);
    const call = (expected: number) =>
      api.POST(
        "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/draw",
        {
          ...at(id),
          body: { expected_draw_counter: expected, target: "pairs" },
        },
      );

    const stale = await failure(dataOf(call(before.draw_counter - 1)));
    const after = await dataOf(call(before.draw_counter));

    expect(stale.status).toBe(409);
    expect(stale.code).toBe("draw_counter_changed");
    expect(after.draw_counter).toBe(before.draw_counter + 1);
  });

  it("reorders the seeds by hand and refuses an order that is out of date", async () => {
    const id = await createDraft();
    await pickPlayers(id, 12);
    const entries = (await tournamentOf(id)).entries;
    const reversed = entries.map((entry) => entry.id).reverse();
    const put = (entry_ids: string[]) =>
      dataOf(
        api.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/seed-order",
          { ...at(id), body: { entry_ids } },
        ),
      );

    await put(reversed);
    const stale = await failure(put(reversed.slice(1)));

    const after = await tournamentOf(id);
    expect(after.entries.map((e) => [e.id, e.seed])).toEqual(
      reversed.map((entryId, index) => [entryId, index + 1]),
    );
    expect(stale.status).toBe(409);
  });

  it("generates a round robin, starts it on the fields, and goes back to setup until a result", async () => {
    const id = await createDraft();
    const setup = await pickPlayers(id, 12);
    const start = (expected: number) =>
      dataOf(
        api.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/start",
          { ...at(id), body: { expected_draw_counter: expected } },
        ),
      );
    const back = () =>
      dataOf(
        api.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/back-to-setup",
          { ...at(id), body: { expected_state: "in_progress" } },
        ),
      );

    const stale = await failure(start(setup.draw_counter + 1));
    const started = await start(setup.draw_counter);
    expect(stale.status).toBe(409);
    expect(started.state).toBe("in_progress");
    expect(started.rounds).toHaveLength(5);
    expect(started.rounds[0]?.matches).toHaveLength(3);
    expect(started.fields.every((f) => f.match_id !== null)).toBe(true);

    expect((await back()).state).toBe("setup");
    expect((await tournamentOf(id)).rounds).toEqual([]);

    await start(setup.draw_counter);
    const running = await tournamentOf(id);
    const matchId = running.fields[0]?.match_id ?? "";
    await dataOf(
      provisionalApi.PUT(
        "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/matches/{match_id}/result",
        {
          params: { path: { ...league, tournament_id: id, match_id: matchId } },
          body: {
            walkover_winner: null,
            games: [{ winner: "side_1", score_1: 10, score_2: 4 }],
          },
        },
      ),
    );
    const refused = await failure(back());
    expect([refused.status, refused.code, refused.detail]).toEqual([
      422,
      "tournament_has_results",
      { results: 1 },
    ]);
  });

  it("generates the first round of a Monster DYP and a knockout bracket with byes", async () => {
    const monster = await createDraft({
      type: "monster_dyp",
      group_phase: "monster_dyp",
    });
    const monsterSetup = await pickPlayers(monster, 9);
    const knockout = await createDraft({
      type: "singles",
      group_phase: "none",
    });
    await pickPlayers(knockout, 6);
    const run = (id: string, expected: number) =>
      dataOf(
        api.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/start",
          { ...at(id), body: { expected_draw_counter: expected } },
        ),
      );

    const first = await run(monster, monsterSetup.draw_counter);
    const bracket = await run(knockout, (await setupOf(knockout)).draw_counter);

    // 9 players: two groups of four, one sits out.
    expect(first.rounds).toHaveLength(1);
    expect(first.rounds[0]?.matches).toHaveLength(2);
    expect(first.rounds[0]?.sitting_out).toHaveLength(1);
    // 6 entries: a bracket of 8, seeds 1 and 2 have byes, so 2 first-round matches.
    expect(bracket.rounds.map((round) => round.matches.length)).toEqual([
      2, 2, 1,
    ]);
  });

  it("answers with the backend's codes: a removed player, a stale pair, incomplete halves", async () => {
    const dyp = await createDraft();
    const ranking = (await setupOf(dyp)).ranking.map((row) => row.player_id);
    // BR-002: a player picked for an unfinished tournament cannot be removed,
    // so the one who is removed here is new.
    const added = await dataOf(
      api.POST("/api/v1/leagues/{league_id}/players", {
        params: { path: league },
        body: { name: "Removed Rita" },
      }),
    );
    const removedId = added.id;
    await dataOf(
      api.PUT("/api/v1/leagues/{league_id}/players/{player_id}/removed", {
        params: { path: { ...league, player_id: removedId } },
        body: { removed: true },
      }),
    );
    const removed = await failure(
      dataOf(
        api.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/players",
          { ...at(dyp), body: { player_ids: [removedId] } },
        ),
      ),
    );
    const picked = await dataOf(
      api.PUT(
        "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/players",
        { ...at(dyp), body: { player_ids: ranking.slice(1, 5) } },
      ),
    );
    const halves = await dataOf(
      api.PUT(
        "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/halves",
        {
          ...at(dyp),
          body: {
            method: "by_hand",
            halves: [{ player_id: nth(ranking, 1), half: "top" }],
          },
        },
      ),
    );
    const incomplete = await failure(
      dataOf(
        api.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/draw",
          {
            ...at(dyp),
            body: {
              expected_draw_counter: halves.draw_counter,
              target: "pairs",
            },
          },
        ),
      ),
    );
    const pairs = await failure(
      dataOf(
        api.PUT(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/pairs",
          { ...at(dyp), body: { pairs: [] } },
        ),
      ),
    );

    expect([removed.status, removed.code]).toEqual([409, "player_removed"]);
    expect(picked.entries).toHaveLength(2);
    expect(halves.entries).toEqual([]);
    expect([incomplete.status, incomplete.detail]).toEqual([
      422,
      { missing: 3 },
    ]);
    expect([pairs.status, pairs.code]).toEqual([
      409,
      "tournament_type_changed",
    ]);
  });

  it("answers 422 nothing_to_pair when fewer than two Doubles players are left", async () => {
    const doubles = await createDraft({ type: "doubles" });
    const picked = await pickPlayers(doubles, 3);
    const first = nth(picked.ranking, 0).player_id;
    const second = nth(picked.ranking, 1).player_id;
    const paired = await dataOf(
      api.PUT(
        "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/pairs",
        { ...at(doubles), body: { pairs: [[first, second]] } },
      ),
    );

    const refused = await failure(
      dataOf(
        api.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/draw",
          {
            ...at(doubles),
            body: {
              expected_draw_counter: paired.draw_counter,
              target: "pairs",
            },
          },
        ),
      ),
    );

    expect([refused.status, refused.code, refused.detail]).toEqual([
      422,
      "nothing_to_pair",
      { unpaired: 1 },
    ]);
    expect((await setupOf(doubles)).draw_counter).toBe(paired.draw_counter);
  });

  it("deletes a tournament, and a repeated delete is a 404", async () => {
    const id = await createDraft();
    const remove = () =>
      api.DELETE(
        "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
        at(id),
      );

    expect((await remove()).response.status).toBe(204);
    expect((await remove()).response.status).toBe(404);
  });
});
