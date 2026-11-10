import { describe, expect, it } from "vitest";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

import {
  DEMO_LEAGUE_ID,
  DEMO_SEASON_ID,
  DEMO_SHARE_TOKEN,
  demoId,
} from "./ids";

const league = { league_id: DEMO_LEAGUE_ID };

async function tournamentsOfSeason() {
  return dataOf(
    provisionalApi.GET(
      "/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments",
      { params: { path: { ...league, season_id: DEMO_SEASON_ID } } },
    ),
  );
}

async function tournament(id: string) {
  return dataOf(
    provisionalApi.GET(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
      { params: { path: { ...league, tournament_id: id } } },
    ),
  );
}

describe("the demo's fake API", () => {
  it("serves one league with 16 players and its active season", async () => {
    const leagues = await dataOf(provisionalApi.GET("/api/v1/leagues"));
    const players = await dataOf(
      provisionalApi.GET("/api/v1/leagues/{league_id}/players", {
        params: { path: league },
      }),
    );

    expect(leagues).toHaveLength(1);
    expect(leagues[0]).toMatchObject({
      id: DEMO_LEAGUE_ID,
      name: "Thursday Foosball",
      player_count: 16,
    });
    expect(leagues[0]?.active_season).toMatchObject({
      number: 1,
      state: "active",
    });
    expect(players).toHaveLength(16);
  });

  it("has two finished tournaments with places and a DYP running its round robin", async () => {
    const summaries = await tournamentsOfSeason();
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
      summaries.map((t) => tournament(t.id)),
    );
    expect(singles?.places?.map((row) => row.place)).toHaveLength(6);
    // §5.1: the semifinal losers share 3rd and split 6 + 4 points.
    expect(
      autumn?.places
        ?.filter((row) => row.place === 3)
        .map((row) => row.points_per_player),
    ).toEqual([5, 5]);
    expect(running?.places).toBeNull();
    expect(running?.entries).toHaveLength(6);
    expect(running?.rounds).toHaveLength(5);
    expect(running?.fields.every((field) => field.match_id !== null)).toBe(
      true,
    );
    expect(running?.waiting.length).toBeGreaterThan(0);
  });

  it("frees a field and fills it with the next waiting match on a result (FR-094)", async () => {
    const running = (await tournamentsOfSeason())[2];
    const before = await tournament(running?.id ?? "");
    const field = before.fields[0];
    const matchId = field?.match_id ?? "";

    const match = await dataOf(
      provisionalApi.PUT(
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
      provisionalApi.GET("/api/v1/public/{share_token}", {
        params: { path: { share_token: DEMO_SHARE_TOKEN } },
      }),
    );

    expect(shared.name).toBe("Thursday Foosball");
    expect(shared.tournaments.every((t) => t.state !== "setup")).toBe(true);
    expect(shared.standings[0]?.place).toBe(1);
  });

  it("keeps each area's seed ids in its own range", () => {
    expect(demoId(1000, "setup")).toBe("019a0000-0000-7000-8000-0000000003e8");
    expect(() => demoId(1000, "foundation")).toThrow(RangeError);
    expect(() => demoId(2999.5, "play")).toThrow(RangeError);
    expect(() => demoId(5000, "outside")).toThrow(RangeError);
  });
});
