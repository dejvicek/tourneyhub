import { describe, expect, it } from "vitest";

import { api, ApiError, dataOf } from "@/api/client";
import type { components } from "@/api/schema";
import { onField, runningDyp } from "@/test/play";

import { DEMO_LEAGUE_ID } from "./ids";

type ResultWrite = components["schemas"]["ResultWrite"];

const tournamentPath = () => ({
  league_id: DEMO_LEAGUE_ID,
  tournament_id: runningDyp().id,
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

function putResult(matchId: string, body: ResultWrite) {
  return dataOf(
    api.PUT(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/matches/{match_id}/result",
      { params: { path: { ...tournamentPath(), match_id: matchId } }, body },
    ),
  );
}

describe("the fake API for results and finishing (the backend's codes, P8)", () => {
  it("refuses a result that breaks a rule with the backend's code", async () => {
    const { match } = onField(1);

    const mismatch = await failure(
      putResult(match.id, {
        walkover_winner: null,
        games: [{ winner: "side_1", score_1: 3, score_2: 10 }],
      }),
    );
    const unfit = await failure(
      putResult(match.id, {
        walkover_winner: null,
        games: [
          { winner: "side_1", score_1: null, score_2: null },
          { winner: "side_1", score_1: null, score_2: null },
        ],
      }),
    );

    expect([mismatch.status, mismatch.code, mismatch.detail]).toEqual([
      422,
      "game_score_mismatch",
      { game_no: 1 },
    ]);
    expect([unfit.status, unfit.code]).toEqual([
      422,
      "result_does_not_fit_format",
    ]);
  });

  it("saves a result and serves the play read with the standings", async () => {
    const { match } = onField(1);

    const saved = await putResult(match.id, {
      walkover_winner: null,
      games: [{ winner: "side_2", score_1: 4, score_2: 10 }],
    });
    const play = await dataOf(
      api.GET("/api/v1/leagues/{league_id}/tournaments/{tournament_id}/play", {
        params: { path: tournamentPath() },
      }),
    );

    expect(saved.outcome).toBe("side_2");
    expect(play.waiting.map((w) => w.match_id)).not.toContain(match.id);
    expect(play.standings.length).toBeGreaterThan(0);
    expect(play.group_done).toBe(false);
  });

  it("refuses to finish before every match has a result", async () => {
    const refused = await failure(
      dataOf(
        api.POST(
          "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/finish",
          {
            params: { path: tournamentPath() },
            body: { expected_state: "in_progress" },
          },
        ),
      ),
    );

    expect([refused.status, refused.code]).toEqual([
      422,
      "group_phase_not_done",
    ]);
    expect(refused.detail.matches_left).toBeGreaterThan(0);
  });
});
