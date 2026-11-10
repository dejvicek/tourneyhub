// Test helpers of the play screens (screens 6–8): the running DYP of the
// demo's seed.
import { generatePath } from "react-router";

import { DEMO_LEAGUE_ID } from "@/demo/ids";
import { db } from "@/demo/store";
import { paths } from "@/lib/paths";

export function runningDyp() {
  const t = db().tournaments.find((row) => row.name === "Thursday DYP");
  if (!t) {
    throw new Error("The seed has no running tournament");
  }
  return t;
}

export function playPath(
  path: string,
  extra: Record<string, string> = {},
): string {
  return generatePath(path, {
    leagueId: DEMO_LEAGUE_ID,
    tournamentId: runningDyp().id,
    ...extra,
  });
}

export function onField(number: number) {
  const t = runningDyp();
  const field = t.fields.find((f) => f.number === number);
  const match = t.rounds
    .flatMap((r) => r.matches)
    .find((m) => m.id === field?.match_id);
  if (!field || !match) {
    throw new Error(`Field ${String(number)} has no match`);
  }
  return { field, match };
}

/** Plays every group match still open, side 1 winning 10:5. */
export function playEverything(): void {
  const t = runningDyp();
  for (const match of t.rounds.flatMap((r) => r.matches)) {
    if (match.outcome === null) {
      match.outcome = "side_1";
      match.games = [{ game_no: 1, winner: "side_1", score_1: 10, score_2: 5 }];
      match.result_entered_at = "2026-11-10T20:00:00Z";
    }
  }
  t.fields = t.fields.map((f) => ({ ...f, match_id: null }));
}

export { paths };
