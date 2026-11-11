import { describe, expect, it } from "vitest";

import type { PhaseSummary, TournamentState } from "@/demo/contract";

import {
  tournamentHome,
  tournamentTabs,
  type TournamentView,
} from "./tournamentViews";

const group = (format: PhaseSummary["format"]): PhaseSummary => ({
  id: "group",
  position: 1,
  kind: "group",
  format,
});
const knockout: PhaseSummary = {
  id: "knockout",
  position: 2,
  kind: "knockout",
  format: "single_elimination",
};

function tournament(
  state: TournamentState,
  phases: PhaseSummary[],
  current: string | null,
  done = false,
): TournamentView {
  return {
    id: "t",
    season_id: "s",
    name: "Thursday",
    date: "2026-11-10",
    type: "dyp",
    state,
    phases,
    current_phase_id: current,
    current_phase_done: done,
  };
}

describe("tournamentHome", () => {
  it.each([
    [
      "setup",
      tournament("setup", [group("round_robin")], null),
      "setupPlayers",
    ],
    [
      "a running round robin",
      tournament("in_progress", [group("round_robin")], "group"),
      "schedule",
    ],
    [
      "a running Swiss",
      tournament("in_progress", [group("swiss")], "group"),
      "betweenRounds",
    ],
    [
      "a running Monster DYP",
      tournament("in_progress", [group("monster_dyp")], "group"),
      "betweenRounds",
    ],
    [
      "a round robin whose group phase is done",
      tournament("in_progress", [group("round_robin")], "group", true),
      "groupPhaseDone",
    ],
    [
      "a Swiss between rounds",
      tournament("in_progress", [group("swiss")], "group", true),
      "betweenRounds",
    ],
    [
      "a Monster DYP between rounds",
      tournament("in_progress", [group("monster_dyp")], "group", true),
      "betweenRounds",
    ],
    [
      "a running knockout",
      tournament("in_progress", [group("round_robin"), knockout], "knockout"),
      "knockout",
    ],
    [
      "a knockout without a group phase",
      tournament("in_progress", [{ ...knockout, position: 1 }], "knockout"),
      "knockout",
    ],
    [
      "a finished tournament",
      tournament("finished", [group("round_robin")], "group", true),
      "finished",
    ],
  ] as const)("opens %s on %s", (_, t, screen) => {
    expect(tournamentHome(t)).toBe(screen);
  });
});

describe("tournamentTabs", () => {
  const labels = (t: TournamentView) =>
    tournamentTabs(t).map((tab) => tab.label);

  it("shows no tabs in setup", () => {
    expect(labels(tournament("setup", [group("round_robin")], null))).toEqual(
      [],
    );
  });

  it("shows Schedule, Fields and Standings for a running round robin", () => {
    expect(
      labels(tournament("in_progress", [group("round_robin")], "group")),
    ).toEqual(["schedule", "fields", "standings"]);
  });

  it("shows Rounds, Fields, Players and Standings for Swiss and Monster DYP", () => {
    expect(
      labels(tournament("in_progress", [group("monster_dyp")], "group")),
    ).toEqual(["rounds", "fields", "players", "standings"]);
  });

  it("adds the knockout once it exists, without Players", () => {
    expect(
      labels(tournament("in_progress", [group("swiss"), knockout], "knockout")),
    ).toEqual(["rounds", "knockout", "fields", "standings"]);
  });

  it("puts the places first and drops Fields once finished", () => {
    expect(
      labels(
        tournament("finished", [group("round_robin"), knockout], "knockout"),
      ),
    ).toEqual(["places", "schedule", "knockout", "standings"]);
  });
});
