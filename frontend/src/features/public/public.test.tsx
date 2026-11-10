import { screen, within } from "@testing-library/react";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { DEMO_SHARE_TOKEN, demoId } from "@/demo/ids";
import { db } from "@/demo/store";
import { axeViolations } from "@/features/auth/axeCheck";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { renderAt } from "@/test/renderApp";

const league = generatePath(paths.publicLeague, {
  shareToken: DEMO_SHARE_TOKEN,
});
const running = generatePath(paths.publicTournament, {
  shareToken: DEMO_SHARE_TOKEN,
  tournamentId: demoId(400, "foundation"),
});

/** A tournament in setup, which only the organizer may see (FR-070). */
function addSetupTournament(): string {
  const [first] = db().tournaments;
  if (first === undefined) {
    throw new Error("The seed has tournaments");
  }
  const id = demoId(4500, "outside");
  db().tournaments.push({
    ...first,
    id,
    name: "Secret Setup Cup",
    state: "setup",
  });
  return id;
}

describe("share-link views", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("FR-070: shows the league, the live fields and the standings, without setup tournaments", async () => {
    addSetupTournament();
    renderAt(league);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Thursday Foosball",
      }),
    ).toBeInTheDocument();
    const live = await screen.findByRole("article", { name: "Thursday DYP" });
    expect(await within(live).findByText("Field 1")).toBeInTheDocument();
    // A header row and at least one player.
    expect(
      within(screen.getByRole("table")).getAllByRole("row").length,
    ).toBeGreaterThan(1);
    expect(screen.getByRole("link", { name: /October Singles/ })).toBeVisible();
    expect(screen.queryByText("Secret Setup Cup")).not.toBeInTheDocument();
  });

  it("FR-070: a setup tournament's own link finds nothing", async () => {
    const id = addSetupTournament();
    renderAt(
      generatePath(paths.publicTournament, {
        shareToken: DEMO_SHARE_TOKEN,
        tournamentId: id,
      }),
    );

    expect(
      await screen.findByText(
        "This tournament is not shared, or the link is wrong.",
      ),
    ).toBeInTheDocument();
  });

  it("FR-070, FR-072: a running tournament shows fields, queue, standings and results, and no organizer controls", async () => {
    renderAt(running);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Thursday DYP" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Waiting for a field" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Round 1" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Main" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Account/ })).toBeNull();
  });

  it.each([
    ["league", league, "Thursday Foosball"],
    ["tournament", running, "Thursday DYP"],
  ])("the %s view has no axe violations", async (_, path, title) => {
    renderAt(path);
    await screen.findByRole("heading", { level: 1, name: title });
    await screen.findAllByRole("table");

    expect(await axeViolations()).toEqual([]);
  });
});
