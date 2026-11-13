import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { beforeEach, describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { stubViewport } from "@/test/media";
import {
  onField,
  paths,
  playEverything,
  playPath,
  runningDyp,
} from "@/test/play";
import { renderAt } from "@/test/renderApp";

// The first screen of a file loads its lazy route, slowly under a full run.
configure({ asyncUtilTimeout: 3000 });

describe("the running round robin (screen 6)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("shows progress, the fields and the schedule by round", async () => {
    renderAt(playPath(paths.schedule));

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Round robin in progress",
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("7 of 15 matches played"),
    ).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "7",
    );
    const fields = screen.getByRole("region", { name: "On the fields" });
    expect(within(fields).getAllByRole("listitem")).toHaveLength(2);
    const round3 = screen.getByRole("region", { name: "Round 3" });
    expect(
      within(round3).getByText("1 played, 2 on fields"),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Round 1" })).toHaveTextContent(
      "3 of 3 played",
    );
  });

  it("shows the live standings beside the schedule from the tablet up (FR-060)", async () => {
    stubViewport(1280);
    renderAt(playPath(paths.schedule));

    const table = await screen.findByRole("table", { name: "Standings" });
    expect(within(table).getAllByRole("row")).toHaveLength(7);
  });

  it("hides the game-difference column in BO1 (BR-101)", async () => {
    stubViewport(1280);
    renderAt(playPath(paths.schedule));

    const table = await screen.findByRole("table", { name: "Standings" });
    expect(
      within(table).queryByRole("columnheader", { name: "Game difference" }),
    ).not.toBeInTheDocument();
  });

  it("shows the game-difference column in BO3 (BR-101)", async () => {
    for (const phase of runningDyp().phases) {
      phase.match_format = "bo3";
    }
    stubViewport(1280);
    renderAt(playPath(paths.schedule));

    const table = await screen.findByRole("table", { name: "Standings" });
    expect(
      within(table).getByRole("columnheader", { name: "Game difference" }),
    ).toBeInTheDocument();
  });

  it("links to the end of the group phase once every match is played (FR-040)", async () => {
    playEverything();
    renderAt(playPath(paths.schedule));

    expect(
      await screen.findByRole("link", {
        name: "See the final standings and what comes next",
      }),
    ).toHaveAttribute("href", playPath(paths.groupPhaseDone));
  });
});

type DemoMatch = ReturnType<
  typeof runningDyp
>["rounds"][number]["matches"][number];

/** Clears every result, so a test sets only the ones it needs. */
function clearResults(): DemoMatch[][] {
  const t = runningDyp();
  for (const match of t.rounds.flatMap((r) => r.matches)) {
    match.outcome = null;
    match.games = [];
    match.is_walkover = false;
    match.result_entered_at = null;
  }
  t.fields = t.fields.map((f) => ({ ...f, match_id: null }));
  return t.rounds.map((r) => r.matches);
}

/** Enters a result: the games' scores, side 1 first; the winner of most games wins. */
function enter(match: DemoMatch, ...scores: [number, number][]): void {
  match.games = scores.map(([score_1, score_2], index) => ({
    game_no: index + 1,
    winner: score_1 > score_2 ? "side_1" : "side_2",
    score_1,
    score_2,
  }));
  const won = scores.filter(([a, b]) => a > b).length;
  match.outcome = won * 2 > scores.length ? "side_1" : "side_2";
  match.result_entered_at = "2026-11-10T20:00:00Z";
}

function at<T>(items: readonly T[] | undefined, index: number): T {
  const item = items?.[index];
  if (item === undefined) {
    throw new Error(`No item ${String(index)}`);
  }
  return item;
}

describe("the standings notes (BR-101)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("says when game difference ranks entries level on points", async () => {
    for (const phase of runningDyp().phases) {
      phase.match_format = "bo3";
    }
    const rounds = clearResults();
    // Two winners that did not meet: 2:0 is ahead of 2:1.
    enter(at(at(rounds, 0), 0), [10, 5], [10, 5]);
    enter(at(at(rounds, 0), 1), [10, 5], [5, 10], [10, 5]);
    renderAt(playPath(paths.tournamentStandings));

    expect(
      (await screen.findAllByText(/ahead of .+ on game difference\./)).length,
    ).toBeGreaterThan(0);
  });

  it("shows both results when two entries met twice (#75 Q35)", async () => {
    const rounds = clearResults();
    const first = at(at(rounds, 0), 0);
    const [a, b] = first.sides;
    const second = at(at(rounds, 1), 0);
    const third = at(at(rounds, 2), 0);
    const fourth = at(at(rounds, 3), 0);
    const others = at(at(rounds, 0), 1).sides;
    // A beats B in rounds 1 and 2; B beats two others, so both have 4 points
    // and their own matches decide.
    enter(first, [10, 8]);
    second.sides = [{ ...b }, { ...a }];
    enter(second, [5, 10]);
    third.sides = [{ ...b }, { ...others[0] }];
    enter(third, [10, 0]);
    fourth.sides = [{ ...b }, { ...others[1] }];
    enter(fourth, [10, 0]);
    renderAt(playPath(paths.tournamentStandings));

    expect(
      await screen.findByText(
        /ahead of .+ on head-to-head: 10:8 in round 1, 10:5 in round 2\./,
      ),
    ).toBeInTheDocument();
  });
});

describe("group phase done (screen 8)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("finishes the tournament after confirming (FR-040)", async () => {
    const user = userEvent.setup();
    playEverything();
    const view = renderAt(playPath(paths.groupPhaseDone));

    await user.click(
      await screen.findByRole(
        "radio",
        { name: "Finish the tournament now" },
        { timeout: 3000 },
      ),
    );
    await user.click(
      screen.getByRole("button", { name: "Finish the tournament" }),
    );
    const confirm = await screen.findByRole("alertdialog", {
      name: "Finish the tournament now?",
    });
    expect(runningDyp().state).toBe("in_progress");
    await user.click(
      within(confirm).getByRole("button", { name: "Finish the tournament" }),
    );

    await waitFor(() => {
      expect(view.state.location.pathname).toBe(playPath(paths.finished));
    });
    expect(runningDyp().state).toBe("finished");
  });

  it("offers the knockout with the top N and moves the cut line (FR-045, BR-080)", async () => {
    const user = userEvent.setup();
    playEverything();
    const view = renderAt(playPath(paths.groupPhaseDone));

    expect(await screen.findByText("Top 4 go through")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "One fewer" }));
    await user.click(screen.getByRole("button", { name: "One fewer" }));
    expect(screen.getByText("Top 2 go through")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "One fewer" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Draw the knockout" }));

    await waitFor(() => {
      expect(view.state.location.pathname).toBe(playPath(paths.startKnockout));
    });
    expect(view.state.location.search).toBe("?qualifiers=2&thirdPlace=false");
  });
});

// jsdom computes no layout or colours: axe checks names, roles, ARIA and
// labels here; contrast is the tokens' (docs/style/frontend-style.md §5.2).
async function violations(): Promise<string[]> {
  const results = await axe.run(document.body, {
    runOnly: [
      "wcag2a",
      "wcag2aa",
      "wcag21a",
      "wcag21aa",
      "wcag22aa",
      "best-practice",
    ],
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return results.violations.map(
    (v) =>
      `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`,
  );
}

describe("axe on the play screens", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  const screens = [
    ["6 round robin", () => playPath(paths.schedule), "Schedule"],
    ["6b fields", () => playPath(paths.fields), "Waiting for a field"],
    [
      "6c move a match",
      () => playPath(paths.moveMatch, { matchId: onField(1).match.id }),
      "Move this match",
    ],
    ["6d add or remove fields", () => playPath(paths.editFields), "Fields"],
    [
      "7 enter a result",
      () => playPath(paths.scheduleResult, { matchId: onField(1).match.id }),
      "Round 3",
    ],
    [
      "8 group phase done",
      () => {
        playEverything();
        return playPath(paths.groupPhaseDone);
      },
      "What comes next?",
    ],
  ] as const;

  it.each(screens)("%s has no violations", async (_name, path, heading) => {
    renderAt(path());
    await screen.findByRole("heading", { name: new RegExp(heading) });
    expect(await violations()).toEqual([]);
  });

  it("7b best of three has no violations", async () => {
    for (const phase of runningDyp().phases) {
      phase.match_format = "bo3";
    }
    renderAt(playPath(paths.scheduleResult, { matchId: onField(1).match.id }));
    await screen.findByRole("tab", { name: "Winners only" });
    expect(await violations()).toEqual([]);
  });
});
