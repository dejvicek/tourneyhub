import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { delay, http, HttpResponse } from "msw";
import { generatePath } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { provisionalApi } from "@/api/provisional";
import { DEMO_LEAGUE_ID, demoId } from "@/demo/ids";
import { db } from "@/demo/store";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";
import { server } from "@/test/server";

const DYP_EVENING = demoId(3200);
const MONSTER = demoId(3300);
const SWISS = demoId(3450);
const SPRING_CUP = demoId(3600);
const GRAND_PRIX = demoId(3700);
const ROUND_ROBIN_DONE = demoId(3800);

const at = (path: string, tournamentId: string) =>
  generatePath(path, { leagueId: DEMO_LEAGUE_ID, tournamentId });
const root = "/api/v1/leagues/{league_id}/tournaments/{tournament_id}";
const ids = (tournamentId: string) => ({
  league_id: DEMO_LEAGUE_ID,
  tournament_id: tournamentId,
});

/** Plays the DYP evening's final, so that the tournament finishes (FR-037). */
async function playFinal(tournamentId: string): Promise<void> {
  const bracket = await provisionalApi.GET(`${root}/bracket`, {
    params: { path: ids(tournamentId) },
  });
  const final = bracket.data?.rounds.at(-1)?.matches[0];
  const saved = await provisionalApi.PUT(`${root}/matches/{match_id}/result`, {
    params: {
      path: { ...ids(tournamentId), match_id: final?.match_id ?? "" },
    },
    body: {
      walkover_winner: null,
      games: [
        { winner: "side_1", score_1: 10, score_2: 7 },
        { winner: "side_1", score_1: 10, score_2: 5 },
      ],
    },
  });
  expect(saved.response.ok).toBe(true);
}

// jsdom has no layout or colours, so colour-contrast cannot run here; axe
// checks the structure: names, roles, ARIA and labels (guide §6).
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
  return results.violations.map((v) => `${v.id}: ${v.help}`);
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
  // These screens read provisional routes, which only the demo serves.
  vi.stubEnv("VITE_DEMO", "true");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("outside demo mode, where the backend serves the season routes (P10a)", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_DEMO", "");
  });

  /** The paths of every request the page makes while it settles. */
  function requested(): string[] {
    const urls: string[] = [];
    server.events.on("request:start", ({ request }) => {
      urls.push(new URL(request.url).pathname);
    });
    return urls;
  }

  afterEach(() => {
    server.events.removeAllListeners();
  });

  it("shows the season's effect on the finished tournament", async () => {
    await playFinal(DYP_EVENING);
    const calls = requested();
    renderAt(at(paths.finished, DYP_EVENING));

    expect(await screen.findByText(/Top \d+ of \d+/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(calls.filter((p) => p.endsWith("/season-effect"))).toHaveLength(1);
  });

  it("shows the season standings, not a line that they come later", async () => {
    const calls = requested();
    renderAt(generatePath(paths.seasonStandings, { leagueId: DEMO_LEAGUE_ID }));

    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.queryByText(/later version/)).not.toBeInTheDocument();
    expect(calls.filter((p) => p.endsWith("/standings"))).not.toEqual([]);
  });
});

describe("Knockout (screen 9)", () => {
  it("shows 4 entries as the design does: semifinals, the BO3 final on its field, places so far", async () => {
    renderAt(at(paths.knockout, DYP_EVENING));

    // The first test of the file also loads the screens' chunk.
    expect(
      await screen.findByRole(
        "heading",
        { level: 1, name: "Knockout" },
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Semifinal 1", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Semifinal 2")).toBeInTheDocument();
    const final = screen.getByRole("region", { name: "Final" });
    expect(within(final).getByText("Best of 3, Field 1")).toBeInTheDocument();
    expect(
      within(final).getByRole("link", { name: "Enter result, Final" }),
    ).toBeInTheDocument();
    // BR-102: without a third-place match the semifinal losers share 3rd.
    expect(screen.getByText(/^3rd, shared:/)).toBeInTheDocument();
    expect(
      screen.getByText("1st and 2nd are decided by the final."),
    ).toBeInTheDocument();
  });

  it("draws 8 entries with byes as a bracket on a tablet", async () => {
    stubViewport(1024);
    renderAt(at(paths.knockout, SPRING_CUP));

    const bracket = await screen.findByRole("region", { name: "Bracket" });
    expect(within(bracket).getAllByText("Bye")).toHaveLength(2);
    expect(
      within(bracket).getByRole("group", { name: "Quarterfinals" }),
    ).toBeInTheDocument();
    expect(
      within(bracket).getByRole("group", { name: "Semifinals" }),
    ).toBeInTheDocument();
    // The third-place match sits next to the final (BR-044).
    expect(within(bracket).getByText("Third place")).toBeInTheDocument();
    expect(
      within(bracket).getAllByRole("link", { name: /^Enter result/ }),
    ).toHaveLength(2);
  });

  it("draws 16 entries with byes as a bracket on a desktop", async () => {
    stubViewport(1280);
    renderAt(at(paths.knockout, GRAND_PRIX));

    const bracket = await screen.findByRole("region", { name: "Bracket" });
    expect(within(bracket).getAllByText("Bye")).toHaveLength(3);
    for (const round of [
      "Round of 16",
      "Quarterfinals",
      "Semifinals",
      "Final",
    ]) {
      expect(
        within(bracket).getByRole("group", { name: round }),
      ).toBeInTheDocument();
    }
  });

  it("lists one round at a time on a phone when there are 8 or 16 entries", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.knockout, GRAND_PRIX));

    const rounds = await screen.findByRole("radiogroup", {
      name: "Rounds of the knockout",
    });
    // The round with matches to play is open first.
    expect(
      within(rounds).getByRole("radio", { name: "Round of 16" }),
    ).toBeChecked();
    expect(screen.getAllByRole("link", { name: /^Enter result/ })).toHaveLength(
      2,
    );
    expect(screen.getAllByText(/, bye$/)).toHaveLength(3);

    await user.click(within(rounds).getByRole("radio", { name: "Final" }));
    expect(await screen.findByText("Waiting")).toBeInTheDocument();
  });

  it("deletes the knockout only after confirming (FR-046)", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.knockout, DYP_EVENING));

    await user.click(
      await screen.findByRole("button", { name: "Delete the knockout" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Delete the knockout?",
    });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByText("Semifinal 1")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    renderAt(at(paths.knockout, DYP_EVENING));
    await screen.findByText("Semifinal 1");
    expect(await violations()).toEqual([]);
  });
});

describe("Changing a knockout result (FR-053, BR-094)", () => {
  it("corrects a played semifinal and clears it again from the bracket", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.knockout, DYP_EVENING));

    await user.click(
      await screen.findByRole("link", { name: "Change result, Semifinal 1" }),
    );
    const sheet = await screen.findByRole("dialog", { name: "Semifinal 1" });
    await user.click(
      await within(sheet).findByRole("button", { name: "Clear result" }),
    );
    const confirm = await screen.findByRole("alertdialog");
    await user.click(
      within(confirm).getByRole("button", { name: "Clear result" }),
    );

    // The match is open again and its winner no longer plays in the final.
    expect(
      await screen.findByRole("link", { name: "Enter result, Semifinal 1" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Change result, Semifinal 1" }),
    ).not.toBeInTheDocument();
  });

  it("locks a semifinal once the final has a result, and says why", async () => {
    await playFinal(DYP_EVENING);
    renderAt(at(paths.knockout, DYP_EVENING));

    expect(
      await screen.findByRole("link", { name: "Change result, Final" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Change result, Semifinal 1" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText(/^Locked: a later match/)).toHaveLength(2);
  });

  it("refuses the change when the sheet is opened on a locked match", async () => {
    await playFinal(DYP_EVENING);
    const bracket = await provisionalApi.GET(`${root}/bracket`, {
      params: { path: ids(DYP_EVENING) },
    });
    const semifinal = bracket.data?.rounds[0]?.matches[0];
    renderAt(
      generatePath(paths.knockoutResult, {
        leagueId: DEMO_LEAGUE_ID,
        tournamentId: DYP_EVENING,
        matchId: semifinal?.match_id ?? "",
      }),
    );

    const sheet = await screen.findByRole("dialog", { name: "Semifinal 1" });
    expect(
      await within(sheet).findByText("This result is locked"),
    ).toBeInTheDocument();
    expect(
      within(sheet).queryByRole("button", { name: "Clear result" }),
    ).not.toBeInTheDocument();
    const refused = await provisionalApi.PUT(
      `${root}/matches/{match_id}/result`,
      {
        params: {
          path: { ...ids(DYP_EVENING), match_id: semifinal?.match_id ?? "" },
        },
        body: { walkover_winner: null, games: [] },
      },
    );
    expect(refused.response.status).toBe(422);
  });

  it("shows the bracket's seeds in the result sheet, not the setup's (D14)", async () => {
    const bracket = await provisionalApi.GET(`${root}/bracket`, {
      params: { path: ids(DYP_EVENING) },
    });
    const semifinal = bracket.data?.rounds[0]?.matches[0];
    renderAt(
      generatePath(paths.knockoutResult, {
        leagueId: DEMO_LEAGUE_ID,
        tournamentId: DYP_EVENING,
        matchId: semifinal?.match_id ?? "",
      }),
    );

    const sheet = await screen.findByRole("dialog", { name: "Semifinal 1" });
    for (const side of semifinal?.sides ?? []) {
      expect(
        await within(sheet).findByText(`Seed ${String(side.seed)}`),
      ).toBeInTheDocument();
    }
  });
});

describe("The sides a result names (ADR-008, BR-094)", () => {
  it("is refused by the fake API when the entries are not the ones on the match", async () => {
    const bracket = await provisionalApi.GET(`${root}/bracket`, {
      params: { path: ids(DYP_EVENING) },
    });
    const final = bracket.data?.rounds.at(-1)?.matches[0];
    const [one, two] = final?.sides ?? [];
    const put = (expected: [string, string]) =>
      provisionalApi.PUT(`${root}/matches/{match_id}/result`, {
        params: {
          path: { ...ids(DYP_EVENING), match_id: final?.match_id ?? "" },
        },
        body: {
          walkover_winner: null,
          games: [
            { winner: "side_1", score_1: 10, score_2: 7 },
            { winner: "side_1", score_1: 10, score_2: 5 },
          ],
          expected_sides: expected,
        },
      });

    const stale = await put([two?.entry_id ?? "", one?.entry_id ?? ""]);
    const right = await put([one?.entry_id ?? "", two?.entry_id ?? ""]);

    expect(stale.response.status).toBe(409);
    expect(right.response.ok).toBe(true);
  });
});

describe("Lots in the bracket (BR-074, ADR-009)", () => {
  it("marks the seeds a lot decided", async () => {
    const real = await provisionalApi.GET(`${root}/bracket`, {
      params: { path: ids(DYP_EVENING) },
    });
    const bracket = structuredClone(real.data);
    const semifinal = bracket?.rounds[0]?.matches[0];
    if (!semifinal?.sides[0]) {
      throw new Error("the demo's semifinal has sides");
    }
    semifinal.sides[0].decided_by_lot = true;
    server.use(
      http.get(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/bracket",
        () => HttpResponse.json(bracket),
      ),
    );
    renderAt(at(paths.knockout, DYP_EVENING));

    expect(await screen.findAllByText("By lot")).toHaveLength(1);
  });
});

describe("Finished (screen 10)", () => {
  it("shows shared places and season points rounded down", async () => {
    await playFinal(DYP_EVENING);
    renderAt(at(paths.finished, DYP_EVENING));

    const places = await screen.findByRole("region", { name: "Final places" });
    const rows = within(places).getAllByRole("listitem");
    // 1st, 2nd, the two semifinal losers sharing 3rd, then the group order (BR-103, BR-104).
    expect(
      rows.map(
        (row) => within(row).getByText(/^\d+(st|nd|rd|th)$/).textContent,
      ),
    ).toEqual(["1st", "2nd", "3rd", "5th", "6th"]);
    const third = rows[2];
    expect(third).toHaveTextContent("Shared. Lost in the semifinals.");
    // (6 + 4) / 2 = 5 each (BR-111).
    expect(third).toHaveTextContent("+5 each");
    expect(within(third ?? document.body).getAllByText(/ & /)).toHaveLength(2);
    expect(rows[3]).toHaveTextContent("+2 each");
    expect(rows[4]).toHaveTextContent("0");
    expect(screen.getByText(/Both get 10 season points\./)).toBeInTheDocument();
    expect(screen.getByText(/Won the final 2:0 against/)).toBeInTheDocument();
  });

  it("shows the season standings after the tournament, with the change", async () => {
    await playFinal(DYP_EVENING);
    renderAt(at(paths.finished, DYP_EVENING));

    const season = await screen.findByRole("list", {
      name: "Season standings after this tournament",
    });
    expect(within(season).getAllByRole("listitem")).toHaveLength(6);
    expect(within(season).getAllByText(/^\+\d+/).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("link", { name: "See the full season standings" }),
    ).toBeInTheDocument();
  });

  it("still shows the places when the season's effect fails, with a retry of its own", async () => {
    await playFinal(DYP_EVENING);
    server.use(
      http.get(
        "*/api/v1/leagues/:league/tournaments/:tournament/season-effect",
        () => HttpResponse.json({ code: "internal_error" }, { status: 500 }),
      ),
    );
    renderAt(at(paths.finished, DYP_EVENING));

    expect(
      await screen.findByRole("region", { name: "Final places" }),
    ).toBeInTheDocument();
    const season = await screen.findByRole("region", {
      name: /standings$/,
    });
    expect(await within(season).findByRole("alert")).toBeInTheDocument();
    expect(
      within(season).getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("still shows the places while the season's effect is loading", async () => {
    await playFinal(DYP_EVENING);
    server.use(
      http.get(
        "*/api/v1/leagues/:league/tournaments/:tournament/season-effect",
        async () => {
          await delay("infinite");
          return HttpResponse.json([]);
        },
      ),
    );
    renderAt(at(paths.finished, DYP_EVENING));

    expect(
      await screen.findByRole("region", { name: "Final places" }),
    ).toBeInTheDocument();
    const season = screen.getByRole("region", { name: /standings$/ });
    expect(within(season).getByRole("status")).toBeInTheDocument();
  });

  it("names a removed player on the places and in the season standings", async () => {
    await playFinal(DYP_EVENING);
    for (const player of db().players) {
      player.removed_at = "2026-11-01T10:00:00Z";
    }
    renderAt(at(paths.finished, DYP_EVENING));

    const places = await screen.findByRole("region", { name: "Final places" });
    const season = await screen.findByRole("list", {
      name: "Season standings after this tournament",
    });
    await waitFor(() => {
      expect(places).not.toHaveTextContent("Unknown");
    });
    expect(season).not.toHaveTextContent("Unknown");
    expect(places).toHaveTextContent(/[A-Z][a-z]+ [A-Z]\./);
  });

  it("goes back to the tournament's own screen when it is not finished (D21)", async () => {
    const view = renderAt(at(paths.finished, DYP_EVENING));
    await waitFor(() => {
      expect(view.state.location.pathname).toBe(
        at(paths.knockout, DYP_EVENING),
      );
    });
  });

  it("has no axe violations", async () => {
    await playFinal(DYP_EVENING);
    renderAt(at(paths.finished, DYP_EVENING));
    await screen.findByRole("region", { name: "Final places" });
    expect(await violations()).toEqual([]);
  });
});

describe("Between rounds (screen 11)", () => {
  it("shows the standings with the tie-breakers in their order and the cut line", async () => {
    renderAt(at(paths.betweenRounds, MONSTER));

    const table = await screen.findByRole("table", {
      name: "Standings, top 8 go through",
    });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Place", "Player", "Pts", "BH1", "BH2", "Diff"]);
    expect(within(table).getAllByRole("row")).toHaveLength(16);
    expect(within(table).getByText("Disabled")).toBeInTheDocument();
    expect(within(table).getByText("Joined round 2")).toBeInTheDocument();
    expect(
      screen.getByText(
        /These decide, in this order: BH1, BH2, Score difference\./,
      ),
    ).toBeInTheDocument();
  });

  it("recommends rounds from the active players and offers the next steps", async () => {
    renderAt(at(paths.betweenRounds, MONSTER));

    expect(
      await screen.findByRole("heading", { name: "Round 5 is complete" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /For 14 active players we recommend at least 4 rounds, and you have played 5\./,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Add round 6" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Start the knockout" }),
    ).toHaveAttribute("href", at(paths.startKnockout, MONSTER));
    expect(
      screen.getByRole("button", { name: "Finish the tournament" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete round 5" }),
    ).toBeInTheDocument();
  });

  it("adds a round with the expected number, then deletes it after confirming", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.betweenRounds, SWISS));

    await user.click(
      await screen.findByRole("button", { name: "Add round 4" }),
    );
    // Round 4 has no results, so the decision card gives way to its progress.
    expect(
      await screen.findByText("Round 4 is in progress"),
    ).toBeInTheDocument();
    const chips = screen.getByRole("radiogroup", { name: "Round" });
    expect(within(chips).getAllByRole("radio")).toHaveLength(4);

    await user.click(screen.getByRole("button", { name: "Delete round 4" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Delete round 4?",
    });
    await user.click(
      within(dialog).getByRole("button", { name: "Delete round 4" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Round 3 is complete" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        within(screen.getByRole("radiogroup", { name: "Round" })).getAllByRole(
          "radio",
        ),
      ).toHaveLength(3);
    });
  });

  it("finishes the tournament after confirming and shows its places", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.betweenRounds, SWISS));

    await user.click(
      await screen.findByRole("button", { name: "Finish the tournament" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Finish the tournament?",
    });
    await user.click(
      within(dialog).getByRole("button", { name: "Finish the tournament" }),
    );

    expect(
      await screen.findByRole("region", { name: "Final places" }),
    ).toBeInTheDocument();
  });

  it("changes the order of the tie-breakers (FR-043)", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.betweenRounds, SWISS));

    await user.click(
      await screen.findByRole("button", { name: "Change the tie-breakers" }),
    );
    const sheet = await screen.findByRole("dialog", { name: "Tie-breakers" });
    await user.click(within(sheet).getByRole("switch", { name: "BH2 on" }));
    await user.click(
      within(sheet).getByRole("button", { name: "Move Score difference up" }),
    );
    await user.click(within(sheet).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(
        screen.getByText(
          /These decide, in this order: BH1, Score difference\./,
        ),
      ).toBeInTheDocument();
    });
    expect(
      within(screen.getByRole("table")).queryByRole("columnheader", {
        name: "BH2",
      }),
    ).not.toBeInTheDocument();
  });

  it("is written in Czech with Czech plurals", async () => {
    await i18n.changeLanguage("cs");
    renderAt(at(paths.betweenRounds, MONSTER));

    expect(await screen.findByText(/15 hráčů/)).toBeInTheDocument();
    expect(
      screen.getByText(/doporučujeme alespoň 4 kola, odehráno máte 5/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Přidat kolo 6" }),
    ).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    renderAt(at(paths.betweenRounds, MONSTER));
    await screen.findByRole("table");
    expect(await violations()).toEqual([]);
  });
});

describe("Late and disabled players (screen 12)", () => {
  it("disables and enables a player", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.lateAndDisabled, MONSTER));

    expect(
      await screen.findByRole("heading", { name: "15 players, 14 active" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Joined late, in round 2.")).toBeInTheDocument();
    expect(
      screen.getByText("Disabled since round 4. Not drawn into new rounds."),
    ).toBeInTheDocument();

    const disable = screen.getAllByRole("button", { name: /^Disable / })[0];
    const name = (disable?.getAttribute("aria-label") ?? "").replace(
      "Disable ",
      "",
    );
    await user.click(disable ?? document.body);
    expect(await screen.findByRole("status")).toHaveTextContent(
      `${name} is disabled.`,
    );
    expect(
      await screen.findByRole("heading", { name: "15 players, 13 active" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: `Enable ${name}` }));
    expect(
      await screen.findByRole("heading", { name: "15 players, 14 active" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(`${name} is enabled.`);
  });

  it("warns about BH before a late player joins, then adds them from the next round", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.lateAndDisabled, MONSTER));

    await user.click(
      await screen.findByRole("button", { name: "Add a late player" }),
    );
    const sheet = await screen.findByRole("dialog", {
      name: "Add a late player",
    });
    expect(within(sheet).getByText(/play from round 6/)).toBeInTheDocument();
    expect(
      within(sheet).getByText("This may be unfair to others"),
    ).toBeInTheDocument();
    expect(
      within(sheet).getByText(/missed 5 rounds, which earn nothing/),
    ).toBeInTheDocument();

    await user.click(
      within(sheet).getByRole("button", { name: /^Add .* from round 6$/ }),
    );
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "16 players, 15 active" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("status")).toHaveTextContent(
      /was added and plays from round 6/,
    );
  });

  it("has no axe violations", async () => {
    renderAt(at(paths.lateAndDisabled, MONSTER));
    await screen.findByRole("heading", { name: "15 players, 14 active" });
    expect(await violations()).toEqual([]);
  });
});

describe("Start the knockout (screen 13)", () => {
  it("offers the three modes from the rules and previews each", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.startKnockout, MONSTER));

    const modes = await screen.findByRole("radiogroup", {
      name: "How are the knockout teams formed?",
    });
    expect(
      within(modes)
        .getAllByRole("radio")
        .map((radio) => radio.parentElement?.textContent ?? ""),
    ).toHaveLength(3);
    for (const name of ["Seeded pairs", "Singles", "A little mercy"]) {
      expect(
        within(modes).getByRole("radio", { name: new RegExp(`^${name}`) }),
      ).toBeInTheDocument();
    }
    // Not offered until the re-mix is built (issue #63).
    expect(
      within(modes).queryByRole("radio", { name: /^Lord have mercy/ }),
    ).not.toBeInTheDocument();
    // Seeded pairs: 8 players make 4 pairs and semifinals.
    expect(screen.getAllByText("VS")).toHaveLength(2);
    expect(
      screen.getByRole("heading", { name: "Semifinals" }),
    ).toBeInTheDocument();

    await user.click(within(modes).getByRole("radio", { name: /^Singles/ }));
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Quarterfinals" }),
      ).toBeInTheDocument();
    });
    expect(screen.getAllByText("VS")).toHaveLength(4);
  });

  it("says which disabled player can't go through (BR-080)", async () => {
    renderAt(at(paths.startKnockout, MONSTER));
    expect(await screen.findByText(/can't go through/)).toBeInTheDocument();
    expect(screen.getByText(/Round 5 locks/)).toBeInTheDocument();
    // BR-080: only the Monster DYP pair options need an even number.
    expect(
      screen.getByText(/Paired options need an even number/),
    ).toBeInTheDocument();
  });

  it("steps the players by two for pairs and by one for singles", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.startKnockout, MONSTER));

    const value = await screen.findByRole("status", {
      name: "Players who go through",
    });
    expect(value).toHaveTextContent("8");
    await user.click(screen.getByRole("button", { name: "Fewer players" }));
    await waitFor(() => {
      expect(value).toHaveTextContent("6");
    });
    await user.click(screen.getByRole("radio", { name: /^Singles/ }));
    await user.click(screen.getByRole("button", { name: "More players" }));
    await waitFor(() => {
      expect(value).toHaveTextContent("7");
    });
  });

  it("draws the knockout and opens it", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.startKnockout, MONSTER));

    await user.click(
      await screen.findByRole("button", { name: "Draw the knockout" }),
    );
    expect(await screen.findByText("Semifinal 1")).toBeInTheDocument();
  });

  it("takes over screen 8's choices after a round robin and draws the bracket", async () => {
    const user = userEvent.setup();
    renderAt(
      `${at(paths.startKnockout, ROUND_ROBIN_DONE)}?qualifiers=4&thirdPlace=true`,
    );

    await user.click(
      await screen.findByRole("button", { name: "Draw the knockout" }),
    );
    expect(await screen.findByText("Semifinal 1")).toBeInTheDocument();
    expect(screen.getByText("Third place")).toBeInTheDocument();
  });

  it("says that every round robin result locks, not one round (BR-053)", async () => {
    renderAt(`${at(paths.startKnockout, ROUND_ROBIN_DONE)}?qualifiers=4`);

    expect(
      await screen.findByText("Round robin results lock"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Round \d+ locks/)).not.toBeInTheDocument();
  });

  it("counts players after a Singles round robin, with no even-number hint (BR-080)", async () => {
    renderAt(`${at(paths.startKnockout, ROUND_ROBIN_DONE)}?qualifiers=4`);

    expect(
      await screen.findByRole("status", { name: "Players who go through" }),
    ).toHaveTextContent("4");
    expect(screen.getByText("The best in the standings.")).toBeInTheDocument();
    expect(screen.queryByText(/even number/)).not.toBeInTheDocument();
  });

  it("counts pairs after a Doubles round robin, with no even-number hint (BR-080)", async () => {
    const tournament = db().tournaments.find((t) => t.id === ROUND_ROBIN_DONE);
    if (tournament !== undefined) tournament.type = "doubles";
    renderAt(`${at(paths.startKnockout, ROUND_ROBIN_DONE)}?qualifiers=4`);

    expect(
      await screen.findByRole("status", { name: "Pairs who go through" }),
    ).toHaveTextContent("4");
    expect(
      screen.getByRole("button", { name: "Fewer pairs" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "More pairs" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/even number/)).not.toBeInTheDocument();
  });

  it("gives the knockout its format and the final its own (BR-120)", async () => {
    const user = userEvent.setup();
    renderAt(`${at(paths.startKnockout, ROUND_ROBIN_DONE)}?qualifiers=4`);

    await user.click(
      within(
        await screen.findByRole("radiogroup", { name: "Knockout matches" }),
      ).getByRole("radio", { name: "BO3" }),
    );
    await user.click(
      within(screen.getByRole("radiogroup", { name: "Final" })).getByRole(
        "radio",
        { name: "BO5" },
      ),
    );
    await user.click(screen.getByRole("button", { name: "Draw the knockout" }));
    await screen.findByText("Semifinal 1");

    const tournament = await provisionalApi.GET(root, {
      params: { path: ids(ROUND_ROBIN_DONE) },
    });
    expect(
      tournament.data?.phases.find((phase) => phase.kind === "knockout"),
    ).toMatchObject({ match_format: "bo3", final_match_format: "bo5" });
  });

  it("names the entries its preview showed, and leaves the format to the server unless picked", async () => {
    let sent: unknown;
    server.use(
      http.put(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout",
        async ({ request }) => {
          sent = await request.clone().json();
        },
      ),
    );
    const user = userEvent.setup();
    renderAt(`${at(paths.startKnockout, ROUND_ROBIN_DONE)}?qualifiers=4`);

    await user.click(
      await screen.findByRole("button", { name: "Draw the knockout" }),
    );
    await screen.findByText("Semifinal 1");

    const preview = await provisionalApi.GET(`${root}/knockout/preview`, {
      params: {
        path: ids(ROUND_ROBIN_DONE),
        query: { qualifiers: 4, third_place_match: false },
      },
    });
    expect(sent).toMatchObject({
      match_format: null,
      expected_qualifier_ids: preview.data?.entries.map(
        (entry) => entry.members[0]?.entry_id,
      ),
    });
  });

  it("ignores query values it cannot use", async () => {
    renderAt(
      `${at(paths.startKnockout, ROUND_ROBIN_DONE)}?qualifiers=lots&thirdPlace=maybe`,
    );

    expect(
      await screen.findByRole("button", { name: "Draw the knockout" }),
    ).toBeEnabled();
  });

  it("has no axe violations", async () => {
    renderAt(at(paths.startKnockout, MONSTER));
    await screen.findByRole("radiogroup", {
      name: "How are the knockout teams formed?",
    });
    expect(await violations()).toEqual([]);
  });
});

describe("Season standings", () => {
  it("lists the players of the finished tournaments with points, played and wins", async () => {
    renderAt(generatePath(paths.seasonStandings, { leagueId: DEMO_LEAGUE_ID }));

    const table = await screen.findByRole("table", {
      name: "Season standings",
    });
    const rows = within(table).getAllByRole("row");
    expect(rows.length).toBeGreaterThan(1);
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Place", "Player", "Played", "Wins", "Pts"]);
    expect(
      screen.getByText(/after 2 finished tournaments/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Points per place, 1st to 5th: 10, 8, 6, 4, 2/),
    ).toBeInTheDocument();
  });

  it("counts a tournament once it finishes (BR-112)", async () => {
    await playFinal(DYP_EVENING);
    renderAt(generatePath(paths.seasonStandings, { leagueId: DEMO_LEAGUE_ID }));

    expect(
      await screen.findByText(/after 3 finished tournaments/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /DYP evening/ }),
    ).toBeInTheDocument();
  });

  it("names a removed player, whose results still count (BR-002)", async () => {
    for (const player of db().players) {
      player.removed_at = "2026-11-01T10:00:00Z";
    }
    renderAt(generatePath(paths.seasonStandings, { leagueId: DEMO_LEAGUE_ID }));

    const table = await screen.findByRole("table", {
      name: "Season standings",
    });
    const [, ...rows] = within(table).getAllByRole("row");
    expect(rows.length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(table).not.toHaveTextContent("Unknown");
    });
    expect(rows[0]).toHaveTextContent(/[A-Z][a-z]+ [A-Z]\./);
  });

  it("is written in Czech with Czech plurals", async () => {
    await i18n.changeLanguage("cs");
    renderAt(generatePath(paths.seasonStandings, { leagueId: DEMO_LEAGUE_ID }));

    expect(
      await screen.findByText(/po 2 dohraných turnajích/),
    ).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    renderAt(generatePath(paths.seasonStandings, { leagueId: DEMO_LEAGUE_ID }));
    await screen.findByRole("table", { name: "Season standings" });
    expect(await violations()).toEqual([]);
  });
});
