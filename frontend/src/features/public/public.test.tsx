import { QueryClient } from "@tanstack/react-query";
import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { generatePath } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { api } from "@/api/client";
import { axeViolations } from "@/features/auth/axeCheck";
import { publicQueries } from "@/features/public/api";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { TEST_SHARE_TOKEN, testId } from "@/test/fake/ids";
import { db } from "@/test/fake/store";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";
import { server } from "@/test/server";

const league = generatePath(paths.publicLeague, {
  shareToken: TEST_SHARE_TOKEN,
});
const running = generatePath(paths.publicTournament, {
  shareToken: TEST_SHARE_TOKEN,
  tournamentId: testId(400, "foundation"),
});

/** The seeded tournament called `name`, as its share-link page. */
function pageOf(name: string): string {
  const found = db().tournaments.find((t) => t.name === name);
  if (found === undefined) {
    throw new Error(`The seed has no ${name}`);
  }
  return generatePath(paths.publicTournament, {
    shareToken: TEST_SHARE_TOKEN,
    tournamentId: found.id,
  });
}

/** A tournament in setup, which only the organizer may see (FR-070). */
function addSetupTournament(): string {
  const [first] = db().tournaments;
  if (first === undefined) {
    throw new Error("The seed has tournaments");
  }
  const id = testId(4500, "outside");
  db().tournaments.push({
    ...first,
    id,
    name: "Secret Setup Cup",
    state: "setup",
  });
  return id;
}

/**
 * The backend's shape (DATA-MODEL §4): the group phase has no `qualifiers`;
 * the knockout's row, which exists once the knockout is drawn, has them.
 */
function qualifiersOnTheKnockout(tournamentId: string, qualifiers: number) {
  const tournament = db().tournaments.find((t) => t.id === tournamentId);
  const group = tournament?.phases.find((phase) => phase.kind === "group");
  if (tournament === undefined || group === undefined) {
    throw new Error("The seed has this tournament with a group phase");
  }
  group.qualifiers = null;
  tournament.phases.push({
    ...group,
    id: testId(4501, "outside"),
    position: 2,
    kind: "knockout",
    format: "single_elimination",
    sit_out_points: null,
    tiebreakers: null,
    qualifiers,
    third_place_match: false,
  });
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
        shareToken: TEST_SHARE_TOKEN,
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

  it("D02: a Monster DYP shows the organizer's standings, with real points, places and tie-breakers (FR-043)", async () => {
    const monster = db().tournaments.find((t) => t.name === "Monster DYP");
    if (monster === undefined) {
      throw new Error("The seed has a Monster DYP");
    }
    const { data: expected = [] } = await api.GET(
      "/api/v1/public/{share_token}/tournaments/{tournament_id}/standings",
      {
        params: {
          path: { share_token: TEST_SHARE_TOKEN, tournament_id: monster.id },
        },
      },
    );
    renderAt(pageOf("Monster DYP"));

    const table = await screen.findByRole("table", { name: "Standings" });
    // The organizer's tie-breakers, in their order (BR-072).
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Place", "Player", "Pts", "BH1", "BH2", "Diff"]);
    // Place, player, points and the tie-breakers of each row.
    const rows = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell"));
    expect(rows).toHaveLength(expected.length);
    expect(expected[0]?.points).toBeGreaterThan(0);
    expect(rows.at(0)?.[0]).toHaveTextContent("1");
    expect(rows.at(0)?.[2]).toHaveTextContent(String(expected[0]?.points));
    expect(rows.at(0)?.[3]).toHaveTextContent(String(expected[0]?.bh1));
    // Not everyone shares the first place.
    expect(rows.at(-1)?.[0]).not.toHaveTextContent(/^1$/);
  });

  it("FR-060: a Monster DYP's standings render without form and ahead_by", async () => {
    const monster = db().tournaments.find((t) => t.name === "Monster DYP");
    if (monster === undefined) {
      throw new Error("The seed has a Monster DYP");
    }
    const entries = monster.entries.filter((e) => e.stage === "main");
    // PublicStandingRow has no `form` and no `ahead_by`; one row per player.
    server.use(
      http.get(
        "*/api/v1/public/:token/tournaments/:tournamentId/standings",
        () =>
          HttpResponse.json(
            entries.map((entry, index) => ({
              place: index + 1,
              entry_id: entry.id,
              played: 2,
              won: 1,
              drawn: 0,
              lost: 1,
              sat_out: 0,
              points: 3,
              game_difference: 0,
              score_difference: 0,
              bh1: 3,
              bh2: 6,
            })),
          ),
      ),
    );
    renderAt(pageOf("Monster DYP"));

    const table = await screen.findByRole("table", { name: "Standings" });
    expect(within(table).getAllByRole("row")).toHaveLength(entries.length + 1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a Swiss draws the cut line from the knockout's qualifiers when the group phase has none (BR-080)", async () => {
    const swiss = db().tournaments.find((t) => t.name === "Swiss evening");
    if (swiss === undefined) {
      throw new Error("The seed has a Swiss evening");
    }
    qualifiersOnTheKnockout(swiss.id, 3);
    renderAt(pageOf("Swiss evening"));

    const table = await screen.findByRole("table", { name: "Standings" });
    const rows = within(table).getAllByRole("row");
    // The line falls under the third row of players, after the header.
    expect(rows.filter((row) => row.classList.contains("border-b-2"))).toEqual([
      rows[3],
    ]);
  });

  it("the places list a shared place once, with every entry under it", async () => {
    const october = db().tournaments.find((t) => t.name === "October Singles");
    if (october === undefined) {
      throw new Error("The seed has an October Singles");
    }
    const [a, b, c, d] = october.entries;
    if (
      a === undefined ||
      b === undefined ||
      c === undefined ||
      d === undefined
    ) {
      throw new Error("The seed has four entries");
    }
    const reason = { kind: "lost_in_round", round: "semifinal", score: null };
    const row = (entry: { id: string }, place: number, points: number) => ({
      entry_id: entry.id,
      place,
      points_per_player: points,
      reason,
    });
    server.use(
      http.get("*/api/v1/public/:token/tournaments/:id/places", () =>
        HttpResponse.json({
          complete: true,
          rows: [row(a, 1, 10), row(b, 2, 8), row(c, 3, 5), row(d, 3, 5)],
        }),
      ),
    );
    renderAt(pageOf("October Singles"));

    const section = await screen.findByRole("region", {
      name: "Final places",
    });
    const items = within(section).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    const shared = items.at(2);
    if (shared === undefined) {
      throw new Error("The third place has a row");
    }
    expect(shared).toHaveTextContent("3.");
    expect(within(shared).getAllByRole("paragraph")).toHaveLength(2);
  });

  it("public places show partners together (BR-145)", async () => {
    const october = db().tournaments.find((t) => t.name === "October Singles");
    const [a, b, c, d] = october?.entries ?? [];
    if (
      a === undefined ||
      b === undefined ||
      c === undefined ||
      d === undefined
    ) {
      throw new Error("The seed has four entries");
    }
    const reason = (partner: string) => ({
      kind: "lost_in_round",
      round: "semifinal",
      score: null,
      opponent_entry_id: null,
      partner_entry_id: partner,
    });
    const row = (entry: { id: string }, partner: { id: string }) => ({
      entry_id: entry.id,
      place: 3,
      points_per_player: 5,
      reason: reason(partner.id),
    });
    server.use(
      http.get("*/api/v1/public/:token/tournaments/:id/places", () =>
        HttpResponse.json({
          complete: true,
          rows: [row(a, b), row(b, a), row(c, d), row(d, c)],
        }),
      ),
    );
    renderAt(pageOf("October Singles"));

    const section = await screen.findByRole("region", {
      name: "Final places",
    });
    const lines = within(section).getAllByRole("paragraph");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toHaveTextContent(" / ");
    expect(lines[1]).toHaveTextContent(" / ");
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

describe("share-link views, where the backend serves the season routes", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  afterEach(() => {
    server.events.removeAllListeners();
  });

  it("ask for the season standings, which the backend serves (P10a)", async () => {
    const asked: string[] = [];
    server.events.on("request:start", ({ request }) => {
      asked.push(new URL(request.url).pathname);
    });
    renderAt(league);
    await screen.findByRole("heading", {
      level: 1,
      name: "Thursday Foosball",
    });
    await screen.findByRole("article", { name: "Thursday DYP" });
    await screen.findByRole("columnheader", { name: "Wins" });

    expect(asked.some((path) => path.endsWith("/tournaments"))).toBe(true);
    expect(asked.some((path) => path.endsWith("/standings"))).toBe(true);
  });

  it("says that the standings failed to load, not that there are none", async () => {
    server.use(
      http.get("*/api/v1/public/:token/seasons/:season/standings", () =>
        HttpResponse.json({ code: "internal_error" }, { status: 500 }),
      ),
    );
    renderAt(league);

    const section = await screen.findByRole("region", {
      name: "Season standings",
    });
    expect(await within(section).findByRole("alert")).toHaveTextContent(
      "Could not load this.",
    );
    expect(
      screen.queryByText("No finished tournament in this season yet."),
    ).not.toBeInTheDocument();
  });

  it("do not ask for a tournament's knockout or standings on the league page", async () => {
    const asked: string[] = [];
    server.events.on("request:start", ({ request }) => {
      asked.push(new URL(request.url).pathname);
    });
    renderAt(league);
    await screen.findByRole("article", { name: "Thursday DYP" });

    expect(
      asked.filter((path) =>
        /\/tournaments\/[^/]+\/(bracket|standings)$/.test(path),
      ),
    ).toEqual([]);
  });

  it("names the share-link rounds by phase when there is a knockout, and plainly when there is not", async () => {
    renderAt(pageOf("Lord have mercy night"));
    const results = await screen.findByRole("region", { name: "Results" });
    const labels = within(results)
      .getAllByRole("heading", { level: 3 })
      .map((heading) => heading.textContent);

    expect(labels).toContain("Group phase, round 1");
    expect(labels.some((l) => l.startsWith("Knockout, round"))).toBe(true);
    expect(labels).not.toContain("Round 1");
  });

  describe("Lord have mercy knockout (BR-155, FR-070)", () => {
    it("shows a Lord have mercy knockout round by round, read-only (BR-155, FR-070)", async () => {
      const asked: string[] = [];
      server.events.on("request:start", ({ request }) => {
        asked.push(new URL(request.url).pathname);
      });
      renderAt(pageOf("Lord have mercy night"));

      expect(
        await screen.findByRole("heading", { name: "Knockout" }),
      ).toBeInTheDocument();
      const rounds = await screen.findByRole("radiogroup", {
        name: "Rounds of the knockout",
      });
      expect(
        within(rounds).getByRole("radio", { name: "Semifinals" }),
      ).toBeChecked();
      expect(screen.getByText("Semifinal 1")).toBeInTheDocument();
      expect(screen.getByText("Semifinal 2")).toBeInTheDocument();
      // No way to enter or change a result.
      expect(
        screen.queryByRole("link", { name: /(Enter|Change) result/ }),
      ).toBeNull();
      expect(screen.queryByRole("button", { name: /result|Draw/ })).toBeNull();
      expect(
        screen.queryByRole("region", { name: "Bracket" }),
      ).not.toBeInTheDocument();
      expect(asked.some((path) => path.endsWith("/knockout/rounds"))).toBe(
        true,
      );
    });

    it("marks players who left (FR-049)", async () => {
      const tournament = db().tournaments.find(
        (t) => t.name === "Lord have mercy night",
      );
      const leaver = tournament?.entries.find(
        (entry) => entry.stage === "main" && entry.player_ids.length === 1,
      );
      if (leaver === undefined) {
        throw new Error("The seed has main entries");
      }
      leaver.is_disabled = true;
      renderAt(pageOf("Lord have mercy night"));

      await screen.findByRole("radiogroup", { name: "Rounds of the knockout" });
      expect(screen.getAllByText("No longer playing")).toHaveLength(1);
    });

    it("marks who came in for whom (BR-155)", async () => {
      const tournament = db().tournaments.find(
        (t) => t.name === "Lord have mercy night",
      );
      const read = await new QueryClient().query(
        publicQueries.knockoutRounds(
          TEST_SHARE_TOKEN,
          tournament?.id ?? "",
          true,
        ),
      );
      const side = read.rounds[0]?.matches[0]?.sides[0];
      const incoming = side?.player_ids[0] ?? "";
      const out =
        tournament?.entries.find(
          (e) => e.stage === "main" && !e.player_ids.includes(incoming),
        )?.player_ids[0] ?? "";
      if (side !== undefined) {
        side.replacements = [{ player_id: incoming, replaced_player_id: out }];
      }
      server.use(
        http.get("*/api/v1/public/:token/tournaments/:id/knockout/rounds", () =>
          HttpResponse.json(read),
        ),
      );
      const nameOf = (id: string) =>
        db().players.find((p) => p.id === id)?.name ?? "";
      renderAt(pageOf("Lord have mercy night"));

      expect(
        await screen.findByText(`${nameOf(incoming)} in for ${nameOf(out)}`),
      ).toBeInTheDocument();
    });

    it("has no axe violations (BR-155)", async () => {
      renderAt(pageOf("Lord have mercy night"));

      await screen.findByRole("radiogroup", { name: "Rounds of the knockout" });
      expect(await axeViolations()).toEqual([]);
    });

    it("never asks for the bracket (BR-155)", async () => {
      server.use(
        http.get("*/api/v1/public/:token/tournaments/:id/bracket", () =>
          HttpResponse.json({ code: "internal_error" }, { status: 500 }),
        ),
      );
      const asked: string[] = [];
      server.events.on("request:start", ({ request }) => {
        asked.push(new URL(request.url).pathname);
      });
      renderAt(pageOf("Lord have mercy night"));

      await screen.findByRole("radiogroup", { name: "Rounds of the knockout" });
      expect(asked.filter((path) => path.endsWith("/bracket"))).toEqual([]);
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });
});
