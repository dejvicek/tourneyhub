import { screen, within } from "@testing-library/react";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { rankingOf } from "@/demo/finalsEngine";
import { DEMO_SHARE_TOKEN, demoId } from "@/demo/ids";
import { db } from "@/demo/store";
import { axeViolations } from "@/features/auth/axeCheck";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";

const league = generatePath(paths.publicLeague, {
  shareToken: DEMO_SHARE_TOKEN,
});
const running = generatePath(paths.publicTournament, {
  shareToken: DEMO_SHARE_TOKEN,
  tournamentId: demoId(400, "foundation"),
});

/** The seeded tournament called `name`, as its share-link page. */
function pageOf(name: string): string {
  const found = db().tournaments.find((t) => t.name === name);
  if (found === undefined) {
    throw new Error(`The seed has no ${name}`);
  }
  return generatePath(paths.publicTournament, {
    shareToken: DEMO_SHARE_TOKEN,
    tournamentId: found.id,
  });
}

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

  it("FR-071: an unknown share link says that it does not work", async () => {
    renderAt(generatePath(paths.publicLeague, { shareToken: "no-such-token" }));

    expect(
      await screen.findByText(
        "This share link does not work. Ask the organizer for a new one.",
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

  it("D02: a Monster DYP shows the organizer's standings, with real points and places", async () => {
    const monster = db().tournaments.find((t) => t.name === "Monster DYP");
    if (monster === undefined) {
      throw new Error("The seed has a Monster DYP");
    }
    const expected = rankingOf(monster).rows;
    renderAt(pageOf("Monster DYP"));

    const table = await screen.findByRole("table", { name: "Standings" });
    // Place, player, points and the tie-breakers of each row.
    const rows = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell"));
    expect(rows).toHaveLength(expected.length);
    expect(expected[0]?.points).toBeGreaterThan(0);
    expect(rows.at(0)?.[0]).toHaveTextContent("1");
    expect(rows.at(0)?.[2]).toHaveTextContent(String(expected[0]?.points));
    // Not everyone shares the first place.
    expect(rows.at(-1)?.[0]).not.toHaveTextContent(/^1$/);
  });

  it("D03: a knockout shows its bracket and byes as byes, not as 0 : 0 matches", async () => {
    stubViewport(1280);
    renderAt(pageOf("Spring Cup"));

    expect(
      await screen.findByRole("region", { name: "Bracket" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Knockout" }),
    ).toBeInTheDocument();
    expect(await screen.findAllByText(/: bye$/)).not.toHaveLength(0);
    expect(screen.queryByText(/ v \?/)).not.toBeInTheDocument();
    // No group phase, so no standings; and no way to enter a result.
    expect(
      screen.queryByRole("heading", { name: "Standings" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Enter result/ })).toBeNull();
  });

  it("D03: a DYP evening shows its knockout after the group standings", async () => {
    stubViewport(1280);
    renderAt(pageOf("DYP evening"));

    expect(
      await screen.findByRole("heading", { name: "Knockout" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("region", { name: "Bracket" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Standings" }),
    ).toBeInTheDocument();
  });
});
