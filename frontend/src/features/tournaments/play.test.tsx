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
