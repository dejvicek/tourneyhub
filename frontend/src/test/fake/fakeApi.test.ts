import { describe, expect, it } from "vitest";

import { api, dataOf } from "@/api/client";
import { newId } from "@/lib/newId";

import {
  TEST_LEAGUE_ID,
  TEST_SEASON_ID,
  TEST_SHARE_TOKEN,
  testId,
} from "./ids";
import { db } from "./store";

const league = { league_id: TEST_LEAGUE_ID };

async function tournamentsOfSeason() {
  return dataOf(
    api.GET("/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments", {
      params: { path: { ...league, season_id: TEST_SEASON_ID } },
    }),
  );
}

async function tournament(id: string) {
  return dataOf(
    api.GET("/api/v1/leagues/{league_id}/tournaments/{tournament_id}", {
      params: { path: { ...league, tournament_id: id } },
    }),
  );
}

/** The share link's read, which carries the places (PublicTournamentRead). */
async function publicTournament(id: string) {
  return dataOf(
    api.GET("/api/v1/public/{share_token}/tournaments/{tournament_id}", {
      params: { path: { share_token: TEST_SHARE_TOKEN, tournament_id: id } },
    }),
  );
}

async function publicPlaces(id: string) {
  return dataOf(
    api.GET("/api/v1/public/{share_token}/tournaments/{tournament_id}/places", {
      params: { path: { share_token: TEST_SHARE_TOKEN, tournament_id: id } },
    }),
  );
}

describe("the fake API", () => {
  it("serves one league with 16 players and its active season", async () => {
    const leagues = await dataOf(api.GET("/api/v1/leagues"));
    const detail = await dataOf(
      api.GET("/api/v1/leagues/{league_id}", {
        params: { path: league },
      }),
    );
    const players = await dataOf(
      api.GET("/api/v1/leagues/{league_id}/players", {
        params: { path: league },
      }),
    );

    expect(leagues).toEqual([
      { id: TEST_LEAGUE_ID, name: "Thursday Foosball" },
    ]);
    expect(detail).toMatchObject({
      share_token: TEST_SHARE_TOKEN,
      default_field_count: 2,
      seasons: [{ number: 1, state: "active", name: null }],
    });
    expect(players).toHaveLength(16);
  });

  it("keeps player names unique, removed holders included, and renames removed players (BR-001)", async () => {
    const added = await dataOf(
      api.POST("/api/v1/leagues/{league_id}/players", {
        params: { path: league },
        body: { name: "  Zdeněk \u00a0  Nový " },
      }),
    );
    expect(added.name).toBe("Zdeněk Nový");

    const removed = await dataOf(
      api.PUT("/api/v1/leagues/{league_id}/players/{player_id}/removed", {
        params: { path: { ...league, player_id: added.id } },
        body: { removed: true },
      }),
    );
    expect(removed.removed_at).not.toBeNull();

    const listed = (include: boolean) =>
      dataOf(
        api.GET("/api/v1/leagues/{league_id}/players", {
          params: { path: league, query: { include_removed: include } },
        }),
      );
    expect(await listed(false)).toHaveLength(16);
    expect(await listed(true)).toHaveLength(17);

    await expect(
      dataOf(
        api.POST("/api/v1/leagues/{league_id}/players", {
          params: { path: league },
          body: { name: "zdeněk nový" },
        }),
      ),
    ).rejects.toMatchObject({
      status: 422,
      code: "player_name_taken",
      detail: { player_id: added.id, name: "Zdeněk Nový", removed: true },
    });

    const renamed = await dataOf(
      api.PUT("/api/v1/leagues/{league_id}/players/{player_id}/name", {
        params: { path: { ...league, player_id: added.id } },
        body: { name: "Zdeněk Novák" },
      }),
    );
    expect(renamed).toMatchObject({ name: "Zdeněk Novák" });

    await expect(
      dataOf(
        api.PUT("/api/v1/leagues/{league_id}/players/{player_id}/name", {
          params: { path: { ...league, player_id: newId() } },
          body: { name: "X" },
        }),
      ),
    ).rejects.toMatchObject({ status: 404, code: "player_not_found" });
  });

  it("starts a season only from the number it expects, and keeps a closed table (FR-021, BR-011)", async () => {
    // BR-010: a new season only once every tournament is finished.
    for (const tournament of db().tournaments) {
      tournament.state = "finished";
    }
    const stale = dataOf(
      api.POST("/api/v1/leagues/{league_id}/seasons", {
        params: { path: league },
        body: { expected_current_number: 2 },
      }),
    );
    await expect(stale).rejects.toMatchObject({
      status: 409,
      code: "season_number_changed",
      detail: { current_number: 1 },
    });

    const second = await dataOf(
      api.POST("/api/v1/leagues/{league_id}/seasons", {
        params: { path: league },
        body: { expected_current_number: 1 },
      }),
    );
    const closedTable = dataOf(
      api.PUT(
        "/api/v1/leagues/{league_id}/seasons/{season_id}/placement-points",
        {
          params: { path: { ...league, season_id: TEST_SEASON_ID } },
          body: { placement_points: [10, 5] },
        },
      ),
    );

    expect(second).toMatchObject({ number: 2, state: "active" });
    await expect(closedTable).rejects.toMatchObject({
      status: 409,
      code: "season_closed",
    });
  });

  it("has two finished tournaments with places and a DYP running its round robin", async () => {
    // The foundation's three; the screen areas' seed parts follow them.
    const summaries = (await tournamentsOfSeason()).slice(0, 3);
    expect(summaries.map((t) => [t.name, t.type, t.state])).toEqual([
      ["October Singles", "singles", "finished"],
      ["Autumn Open DYP", "dyp", "finished"],
      ["Thursday DYP", "dyp", "in_progress"],
    ]);
    // What a tournament's own path needs to pick its screen.
    expect(
      summaries.map((t) => [
        t.phases.map((phase) => phase.kind),
        t.current_phase_id === t.phases.at(-1)?.id,
        t.current_phase_done,
      ]),
    ).toEqual([
      [["group"], true, true],
      [["group", "knockout"], true, true],
      [["group"], true, false],
    ]);

    const [singles, autumn, running] = await Promise.all(
      summaries.map((t) => publicPlaces(t.id)),
    );
    expect(singles?.rows.map((row) => row.place)).toHaveLength(6);
    // §5.1: the semifinal losers share 3rd and split 6 + 4 points.
    expect(
      autumn?.rows
        .filter((row) => row.place === 3)
        .map((row) => row.points_per_player),
    ).toEqual([5, 5]);
    expect(running?.complete).toBe(false);
    const runningRead = await publicTournament(summaries[2]?.id ?? "");
    expect(runningRead.entries).toHaveLength(6);
    expect(runningRead.rounds).toHaveLength(5);
    expect(runningRead.fields.every((field) => field.match_id !== null)).toBe(
      true,
    );
    expect(runningRead.waiting.length).toBeGreaterThan(0);
  });

  it("frees a field and fills it with the next waiting match on a result (FR-094)", async () => {
    const running = (await tournamentsOfSeason())[2];
    const before = await tournament(running?.id ?? "");
    const field = before.fields[0];
    const matchId = field?.match_id ?? "";

    const match = await dataOf(
      api.PUT(
        "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/matches/{match_id}/result",
        {
          params: {
            path: { ...league, tournament_id: before.id, match_id: matchId },
          },
          body: {
            walkover_winner: null,
            games: [{ winner: "side_1", score_1: 10, score_2: 7 }],
          },
        },
      ),
    );
    const after = await tournament(before.id);

    expect(match.outcome).toBe("side_1");
    expect(after.fields[0]?.match_id).not.toBe(matchId);
    expect(after.waiting).not.toContain(matchId);
  });

  it("serves the share link without tournaments in setup (FR-070)", async () => {
    const shared = await dataOf(
      api.GET("/api/v1/public/{share_token}", {
        params: { path: { share_token: TEST_SHARE_TOKEN } },
      }),
    );
    const path = { share_token: TEST_SHARE_TOKEN, season_id: TEST_SEASON_ID };
    const tournaments = await dataOf(
      api.GET("/api/v1/public/{share_token}/seasons/{season_id}/tournaments", {
        params: { path },
      }),
    );
    const standings = await dataOf(
      api.GET("/api/v1/public/{share_token}/seasons/{season_id}/standings", {
        params: { path },
      }),
    );

    expect(shared.name).toBe("Thursday Foosball");
    expect(shared.seasons.map((season) => season.id)).toContain(TEST_SEASON_ID);
    expect(shared.players).toHaveLength(16);
    expect(tournaments).not.toHaveLength(0);
    expect(tournaments.every((t) => t.state !== "setup")).toBe(true);
    expect(standings[0]?.place).toBe(1);
  });

  it("answers an unknown share token with 404 share_link_not_found (FR-071)", async () => {
    await expect(
      dataOf(
        api.GET("/api/v1/public/{share_token}", {
          params: { path: { share_token: "no-such-token" } },
        }),
      ),
    ).rejects.toMatchObject({
      status: 404,
      code: "share_link_not_found",
      detail: {},
    });
  });

  it("keeps each area's seed ids in its own range", () => {
    expect(testId(1000, "setup")).toBe("019a0000-0000-7000-8000-0000000003e8");
    expect(() => testId(1000, "foundation")).toThrow(RangeError);
    expect(() => testId(2999.5, "play")).toThrow(RangeError);
    expect(() => testId(5000, "outside")).toThrow(RangeError);
  });
});
