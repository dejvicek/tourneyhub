import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, dataOf } from "@/api/client";
import type { components } from "@/api/schema";
import { onField, playEverything, runningDyp } from "@/test/play";

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

  describe("a repeated and a cleared result (ADR-008, BR-134)", () => {
    const won: ResultWrite = {
      walkover_winner: null,
      games: [{ winner: "side_1", score_1: 10, score_2: 4 }],
    };
    const empty: ResultWrite = { walkover_winner: null, games: [] };

    afterEach(() => {
      vi.useRealTimers();
    });

    it("keeps the result time when the same result is sent again", async () => {
      vi.useFakeTimers({ toFake: ["Date"] });
      const { match } = onField(1);
      vi.setSystemTime(new Date("2026-11-12T18:00:00Z"));
      const first = await putResult(match.id, won);
      vi.setSystemTime(new Date("2026-11-12T18:30:00Z"));

      const again = await putResult(match.id, won);
      const changed = await putResult(match.id, {
        ...won,
        games: [{ winner: "side_1", score_1: 10, score_2: 5 }],
      });

      expect(first.result_entered_at).toBe("2026-11-12T18:00:00.000Z");
      expect(again.result_entered_at).toBe(first.result_entered_at);
      expect(changed.result_entered_at).toBe("2026-11-12T18:30:00.000Z");
    });

    it("changes nothing when a match without a result is cleared", async () => {
      const { match, field } = onField(1);

      await putResult(match.id, empty);

      expect(runningDyp().fields.find((f) => f.id === field.id)?.match_id).toBe(
        match.id,
      );
    });

    it("puts a cleared match on a free field when it can be played", async () => {
      playEverything();
      const t = runningDyp();
      const played = t.rounds[0]?.matches[0];

      await putResult(played?.id ?? "", empty);

      expect(played?.outcome).toBeNull();
      expect(t.fields.map((f) => f.match_id)).toContain(played?.id);
    });

    it("reopens a finished tournament and fills the free fields", async () => {
      playEverything();
      const t = runningDyp();
      t.state = "finished";
      const played = t.rounds[0]?.matches[0];

      await putResult(played?.id ?? "", empty);

      expect(t.state).toBe("in_progress");
      expect(t.fields.map((f) => f.match_id)).toContain(played?.id);
    });
  });
});
