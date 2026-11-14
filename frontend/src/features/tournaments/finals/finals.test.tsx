import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { delay, http, HttpResponse } from "msw";
import { generatePath } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { finalsMutations, finalsQueries } from "@/features/finals/api";
import { resultMutations } from "@/features/results/api";
import { shortName } from "@/features/tournaments/finals/names";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { TEST_LEAGUE_ID, testId } from "@/test/fake/ids";
import { db, tournamentRead } from "@/test/fake/store";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";
import { server } from "@/test/server";
import {
  createDraft,
  pickPlayers,
  startTournament,
  tournamentOf,
} from "@/test/setupTestHelpers";

const DYP_EVENING = testId(3200);
const MONSTER = testId(3300);
const SWISS = testId(3450);
const SPRING_CUP = testId(3600);
const GRAND_PRIX = testId(3700);
const ROUND_ROBIN_DONE = testId(3800);
const LHM = testId(3900);

const at = (path: string, tournamentId: string) =>
  generatePath(path, { leagueId: TEST_LEAGUE_ID, tournamentId });
const root = "/api/v1/leagues/{league_id}/tournaments/{tournament_id}";
const ids = (tournamentId: string) => ({
  league_id: TEST_LEAGUE_ID,
  tournament_id: tournamentId,
});

/** Plays the DYP evening's final, so that the tournament finishes (FR-037). */
async function playFinal(tournamentId: string): Promise<void> {
  const bracket = await api.GET(`${root}/bracket`, {
    params: { path: ids(tournamentId) },
  });
  const final = bracket.data?.rounds.at(-1)?.matches[0];
  const saved = await api.PUT(`${root}/matches/{match_id}/result`, {
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
    renderAt(generatePath(paths.seasonStandings, { leagueId: TEST_LEAGUE_ID }));

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

  it("changes the final's format and reloads the bracket (FR-054, BR-120)", async () => {
    const sent: unknown[] = [];
    let bracketReads = 0;
    server.use(
      http.put(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/final-format",
        async ({ request }) => {
          sent.push(await request.clone().json());
          return HttpResponse.json({});
        },
      ),
      http.get(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/bracket",
        () => {
          bracketReads += 1;
        },
      ),
    );
    const user = userEvent.setup();
    renderAt(at(paths.knockout, DYP_EVENING));

    const picker = await screen.findByRole("radiogroup", {
      name: "Format of the final",
    });
    expect(within(picker).getByRole("radio", { name: "BO3" })).toBeChecked();
    const reads = bracketReads;
    await user.click(within(picker).getByRole("radio", { name: "BO5" }));
    await waitFor(() => {
      expect(bracketReads).toBeGreaterThan(reads);
    });
    await user.click(
      within(picker).getByRole("radio", { name: "Same as knockout" }),
    );

    await waitFor(() => {
      expect(sent).toEqual([
        { final_match_format: "bo5" },
        { final_match_format: null },
      ]);
    });
  });

  it("says why the final's format cannot change once it has a result, after the reload hid the control (BR-096)", async () => {
    server.use(
      http.put(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/final-format",
        async () => {
          // Another screen played the final first: the reloaded bracket has its result.
          await playFinal(DYP_EVENING);
          return HttpResponse.json(
            { code: "match_has_result", detail: { match_id: "x" } },
            { status: 409 },
          );
        },
      ),
    );
    const user = userEvent.setup();
    renderAt(at(paths.knockout, DYP_EVENING));

    const picker = await screen.findByRole("radiogroup", {
      name: "Format of the final",
    });
    await user.click(within(picker).getByRole("radio", { name: "BO5" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The final has a result now, so its format cannot change.",
    );
    await waitFor(() => {
      expect(
        screen.queryByRole("radiogroup", { name: "Format of the final" }),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The final has a result now, so its format cannot change.",
    );
  });

  it("offers no format change once the final has a result (FR-054)", async () => {
    await playFinal(DYP_EVENING);
    renderAt(at(paths.knockout, DYP_EVENING));

    await screen.findByRole("link", { name: "Change result, Final" });
    expect(
      screen.queryByRole("radiogroup", { name: "Format of the final" }),
    ).not.toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    renderAt(at(paths.knockout, DYP_EVENING));
    await screen.findByText("Semifinal 1");
    expect(await violations()).toEqual([]);
  });
});

describe("Knockout in Lord have mercy (screen 9, BR-155)", () => {
  const readRounds = () =>
    new QueryClient().query(finalsQueries.knockoutRounds(TEST_LEAGUE_ID, LHM));
  const enterResult = async (matchId: string, bestOf3 = false) => {
    const queryClient = new QueryClient();
    await new MutationObserver(
      queryClient,
      resultMutations.save(TEST_LEAGUE_ID, LHM, matchId),
    ).mutate({
      walkover_winner: null,
      games: Array.from({ length: bestOf3 ? 2 : 1 }, () => ({
        winner: "side_1" as const,
        score_1: 10,
        score_2: 3,
      })),
    });
  };
  /** Gives every match of the newest round that lacks a result one. */
  async function finishNewestRound(): Promise<void> {
    const read = await readRounds();
    for (const match of read.rounds.at(-1)?.matches ?? []) {
      if (match.state === "ready" || match.state === "on_field") {
        await enterResult(match.match_id);
      }
    }
  }
  const drawRound = (expected: number) => {
    const queryClient = new QueryClient();
    return new MutationObserver(
      queryClient,
      finalsMutations.drawKnockoutRound(queryClient, TEST_LEAGUE_ID, LHM),
    ).mutate({ expected_round_no: expected });
  };
  const knockoutPath = () => at(paths.knockout, LHM);

  afterEach(() => {
    server.events.removeAllListeners();
  });

  it("shows the knockout round by round, not as a bracket (BR-155)", async () => {
    const calls: string[] = [];
    server.events.on("request:start", ({ request }) => {
      calls.push(new URL(request.url).pathname);
    });
    renderAt(knockoutPath());

    const rounds = await screen.findByRole("radiogroup", {
      name: "Rounds of the knockout",
    });
    expect(
      within(rounds).getByRole("radio", { name: "Semifinals" }),
    ).toBeChecked();
    expect(screen.getByText("Semifinal 1")).toBeInTheDocument();
    expect(screen.getByText("Semifinal 2")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Change result, Semifinal 1" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Enter result, Semifinal 2" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Bracket" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("radiogroup", { name: "Format of the final" }),
    ).toBeInTheDocument();
    // The bracket answers 422 in this mode, so it is never asked for.
    expect(calls.filter((path) => path.endsWith("/bracket"))).toEqual([]);
    expect(
      calls.filter((path) => path.endsWith("/knockout/rounds")),
    ).not.toEqual([]);
  });

  it("reads a bye as the pair in the team format, then the bye (BR-155)", async () => {
    const read = await readRounds();
    const [first, second] = read.rounds.at(-1)?.matches ?? [];
    if (first === undefined || second === undefined) {
      throw new Error("The seed has no two matches in the newest round.");
    }
    const kept = second.sides[0];
    if (kept === undefined) throw new Error("The match has no side.");
    const byeMatch = {
      ...second,
      state: "bye" as const,
      sides: [
        kept,
        {
          entry_id: null,
          player_ids: [],
          is_bye: true,
          left_player_ids: [],
          replacements: [],
        },
      ],
    };
    const bye = { ...read.rounds.at(-1), matches: [first, byeMatch] };
    server.use(
      http.get(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/rounds",
        () =>
          HttpResponse.json({
            ...read,
            rounds: [...read.rounds.slice(0, -1), bye],
          }),
      ),
    );
    renderAt(knockoutPath());

    expect(kept.player_ids).toHaveLength(2);
    const text = await screen.findByText(/, bye$/);
    expect(text).toHaveTextContent(/^.+ \/ .+, bye$/);
  });

  it("shows the rounds side by side on a desktop, the rounds not drawn yet muted (BR-155)", async () => {
    stubViewport(1280);
    renderAt(knockoutPath());

    const rounds = await screen.findByRole("region", {
      name: "Rounds of the knockout",
    });
    expect(
      within(rounds).getByRole("group", { name: "Semifinals" }),
    ).toBeInTheDocument();
    expect(
      within(rounds).getByText("Drawn after the semifinals"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Knockout" }),
    ).toBeInTheDocument();
  });

  it("offers the next round only when can_draw_next, and draws it with the expected number (BR-140)", async () => {
    const sent: unknown[] = [];
    server.use(
      http.post(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/rounds",
        async ({ request }) => {
          sent.push(await request.clone().json());
        },
      ),
    );
    const user = userEvent.setup();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderAt(knockoutPath(), queryClient);

    expect(
      await screen.findByText("In progress: the semifinals"),
    ).toBeInTheDocument();
    expect(screen.getByText("1 match has no result yet.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Draw the/ }),
    ).not.toBeInTheDocument();

    // The last result of the round arrives; the screen reloads.
    await finishNewestRound();
    await queryClient.invalidateQueries(
      finalsQueries.knockoutRounds(TEST_LEAGUE_ID, LHM),
    );
    expect(await screen.findByText("Semifinals complete")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Draw the final" }));

    expect(await screen.findByText("Third place")).toBeInTheDocument();
    expect(sent).toEqual([{ expected_round_no: 2 }]);
    expect(
      screen.queryByRole("button", { name: /^Draw the/ }),
    ).not.toBeInTheDocument();
  });

  it("shows the new round on a phone after a draw, even if another was picked (BR-140)", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderAt(knockoutPath(), queryClient);

    const rounds = await screen.findByRole("radiogroup", {
      name: "Rounds of the knockout",
    });
    await user.click(within(rounds).getByRole("radio", { name: "Semifinals" }));
    await finishNewestRound();
    await queryClient.invalidateQueries(
      finalsQueries.knockoutRounds(TEST_LEAGUE_ID, LHM),
    );
    await user.click(
      await screen.findByRole("button", { name: "Draw the final" }),
    );

    expect(await screen.findByRole("radio", { name: "Final" })).toBeChecked();
  });

  it("draws the next round in Czech with Czech plurals (BR-140)", async () => {
    await i18n.changeLanguage("cs");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderAt(knockoutPath(), queryClient);

    expect(
      await screen.findByText("1 zápas ještě nemá výsledek."),
    ).toBeInTheDocument();
    await finishNewestRound();
    await queryClient.invalidateQueries(
      finalsQueries.knockoutRounds(TEST_LEAGUE_ID, LHM),
    );
    expect(
      await screen.findByRole("button", { name: /^Vylosovat: / }),
    ).toBeInTheDocument();
  });

  it("shows the 409 round_number_changed text and reloads", async () => {
    await finishNewestRound();
    let reads = 0;
    server.use(
      http.get(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/rounds",
        () => {
          reads += 1;
        },
      ),
      http.post(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/rounds",
        () =>
          HttpResponse.json(
            { code: "round_number_changed", detail: { current_round_no: 2 } },
            { status: 409 },
          ),
      ),
    );
    const user = userEvent.setup();
    renderAt(knockoutPath());

    const draw = await screen.findByRole("button", { name: "Draw the final" });
    const readsBeforeClick = reads;
    await user.click(draw);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The rounds changed on another device, so they were reloaded. Check them and try again.",
    );
    await waitFor(() => {
      expect(reads).toBeGreaterThan(readsBeforeClick);
    });
  });

  it("names how many results deleting the newest round removes (FR-046)", async () => {
    await finishNewestRound();
    const drawn = await drawRound(2);
    const final = drawn.rounds
      .at(-1)
      ?.matches.find((m) => m.kind === "standard");
    await enterResult(final?.match_id ?? "", true);
    const user = userEvent.setup();
    renderAt(knockoutPath());

    await user.click(
      await screen.findByRole("button", { name: "Delete the final" }),
    );

    const dialog = await screen.findByRole("alertdialog", {
      name: "Delete the final?",
    });
    expect(dialog).toHaveTextContent(
      "The drawn pairs and 1 result are removed.",
    );
    expect(dialog).not.toHaveTextContent("deletes the knockout");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("says deleting round 1 deletes the knockout, then opens the tournament (BR-087)", async () => {
    const user = userEvent.setup();
    const view = renderAt(knockoutPath());

    await user.click(
      await screen.findByRole("button", { name: "Delete the semifinals" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Delete the semifinals?",
    });
    expect(dialog).toHaveTextContent(
      "The drawn pairs and 1 result are removed. This deletes the knockout and unlocks the group phase.",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Delete the semifinals" }),
    );

    await waitFor(() => {
      expect(view.state.location.pathname).not.toBe(knockoutPath());
    });
    expect(
      await screen.findByRole("heading", { name: "Round 2 is complete" }),
    ).toBeInTheDocument();
  });

  it("marks players who left and stay in the draw (BR-149)", async () => {
    const read = await readRounds();
    const waiting = read.rounds
      .flatMap((round) => round.matches)
      .find((match) => match.state === "on_field");
    const left = waiting?.sides[0]?.player_ids[0] ?? "";
    const marked = {
      ...read,
      left_player_ids: [left],
      rounds: read.rounds.map((round) => ({
        ...round,
        matches: round.matches.map((match) => ({
          ...match,
          sides: match.sides.map((side) => ({
            ...side,
            left_player_ids: side.player_ids.filter((id) => id === left),
          })),
        })),
      })),
    };
    server.use(
      http.get(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/rounds",
        () => HttpResponse.json(marked),
      ),
    );
    renderAt(knockoutPath());

    expect(
      await screen.findByText(/no longer plays but stays in the draw/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("No longer playing")).toHaveLength(1);
  });

  /** The rounds with the first `count` players marked as having left (BR-149). */
  async function withLeft(count: number): Promise<void> {
    const read = await readRounds();
    const players = read.rounds
      .flatMap((round) => round.matches)
      .flatMap((match) => match.sides)
      .flatMap((side) => side.player_ids);
    server.use(
      http.get(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/rounds",
        () =>
          HttpResponse.json({
            ...read,
            left_player_ids: players.slice(0, count),
          }),
      ),
    );
  }

  it("says several players who left no longer play (BR-149)", async () => {
    await withLeft(2);
    renderAt(knockoutPath());

    expect(
      await screen.findByText(/ no longer play but stay in the draw$/),
    ).toBeInTheDocument();
  });

  it("says in Czech that one player left, and the plural for two (BR-149)", async () => {
    await i18n.changeLanguage("cs");
    await withLeft(1);
    renderAt(knockoutPath());

    expect(
      await screen.findByText(/^Už nehraje, ale zůstává v losování: /),
    ).toBeInTheDocument();
  });

  it("marks fixed winners (BR-146)", async () => {
    const user = userEvent.setup();
    await finishNewestRound();
    await drawRound(2);
    renderAt(knockoutPath());

    const rounds = await screen.findByRole("radiogroup", {
      name: "Rounds of the knockout",
    });
    expect(within(rounds).getByRole("radio", { name: "Final" })).toBeChecked();
    expect(screen.queryByText("Winner fixed")).not.toBeInTheDocument();

    await user.click(within(rounds).getByRole("radio", { name: "Semifinals" }));

    expect(await screen.findAllByText("Winner fixed")).toHaveLength(2);
  });

  it("has no axe violations", async () => {
    renderAt(knockoutPath());
    await screen.findByText("Semifinal 1");
    expect(await violations()).toEqual([]);
  });

  it("has no axe violations in the desktop columns", async () => {
    stubViewport(1280);
    renderAt(knockoutPath());
    await screen.findByRole("region", { name: "Rounds of the knockout" });
    expect(await violations()).toEqual([]);
  });

  it("deletes a later round and stays on the screen, its winners no longer fixed (BR-146, FR-046)", async () => {
    const user = userEvent.setup();
    await finishNewestRound();
    await drawRound(2);
    const view = renderAt(knockoutPath());

    const rounds = await screen.findByRole("radiogroup", {
      name: "Rounds of the knockout",
    });
    await user.click(within(rounds).getByRole("radio", { name: "Semifinals" }));
    expect(await screen.findAllByText("Winner fixed")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Delete the final" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Delete the final?",
    });
    await user.click(
      within(dialog).getByRole("button", { name: "Delete the final" }),
    );

    await waitFor(() => {
      expect(
        screen.queryByRole("radio", { name: "Final" }),
      ).not.toBeInTheDocument();
    });
    expect(view.state.location.pathname).toBe(knockoutPath());
    expect(await screen.findByText("Semifinals complete")).toBeInTheDocument();
    expect(screen.queryByText("Winner fixed")).not.toBeInTheDocument();
  });

  it("opens the tournament after deleting round 1 even when the tournament reloads first (BR-087)", async () => {
    const user = userEvent.setup();
    const view = renderAt(knockoutPath());

    await user.click(
      await screen.findByRole("button", { name: "Delete the semifinals" }),
    );
    const dialog = await screen.findByRole("alertdialog");
    // Every reload but the tournament's own waits for the gate, so the
    // tournament arrives first and the screen swaps to "no knockout" while the
    // delete is still settling. An empty resolver falls through to the fake API.
    let open = (): void => undefined;
    const gate = new Promise<void>((resolve) => {
      open = resolve;
    });
    server.use(
      http.get("/api/v1/*", async ({ request }) => {
        if (!new URL(request.url).pathname.endsWith(LHM)) {
          await gate;
        }
      }),
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Delete the semifinals" }),
    );
    // The rounds view is gone: the tournament no longer has a knockout.
    await waitFor(() => {
      expect(
        screen.queryByRole("button", {
          name: "Delete the semifinals",
          hidden: true,
        }),
      ).not.toBeInTheDocument();
    });
    open();

    await waitFor(() => {
      expect(view.state.location.pathname).toBe(at(paths.tournament, LHM));
    });
  });

  describe("players who left and replacements (FR-044, FR-049, BR-147 to BR-155)", () => {
    const nameOf = (playerId: string) =>
      shortName(db().players.find((p) => p.id === playerId)?.name ?? "");
    /** 4 pairs without a third-place match: the semifinal losers are knocked out. */
    const withoutThirdPlace = () => {
      const knockout = db()
        .tournaments.find((t) => t.id === LHM)
        ?.phases.find((p) => p.kind === "knockout");
      if (knockout === undefined) throw new Error("The seed has a knockout.");
      knockout.third_place_match = false;
    };
    const setDisabled = (entryId: string, disabled = true) => {
      const queryClient = new QueryClient();
      return new MutationObserver(
        queryClient,
        finalsMutations.setDisabled(queryClient, TEST_LEAGUE_ID, LHM),
      ).mutate({ entryId, disabled });
    };
    const openPlayers = async (user: ReturnType<typeof userEvent.setup>) => {
      const toggle = await screen.findByRole("button", {
        name: "Players in the knockout",
      });
      await user.click(toggle);
      return toggle;
    };

    it("lists the knockout's players collapsed, each with what the flag means (FR-044, BR-147)", async () => {
      withoutThirdPlace();
      const user = userEvent.setup();
      renderAt(knockoutPath());

      const toggle = await screen.findByRole("button", {
        name: "Players in the knockout",
      });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByRole("button", { name: /^Disable / })).toBeNull();
      await user.click(toggle);

      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(screen.getAllByRole("button", { name: /^Disable / })).toHaveLength(
        8,
      );
      expect(screen.getAllByText("Still in.")).toHaveLength(6);
      expect(
        screen.getAllByText("Knocked out. Can come in as a replacement."),
      ).toHaveLength(2);
    });

    it("disables a player who left and enables them again, announced, the rounds reloaded (FR-044, BR-147, BR-149)", async () => {
      const read = await readRounds();
      const open = read.rounds[0]?.matches.find((m) => m.state === "on_field");
      const playerId = open?.sides[0]?.player_ids[0] ?? "";
      const name = nameOf(playerId);
      const user = userEvent.setup();
      renderAt(knockoutPath());
      await openPlayers(user);

      await user.click(screen.getByRole("button", { name: `Disable ${name}` }));

      expect(
        await screen.findByText(
          "Has left. Their pair loses this round's match by walkover.",
        ),
      ).toBeInTheDocument();
      // The announcement comes once the change and the reload have settled.
      expect(
        await screen.findByText(`${name} is disabled.`),
      ).toBeInTheDocument();
      // The rounds reloaded: the card marks the player who left (BR-155).
      expect(await screen.findAllByText("No longer playing")).toHaveLength(1);

      await user.click(screen.getByRole("button", { name: `Enable ${name}` }));

      expect(
        await screen.findByText(`${name} is enabled.`),
      ).toBeInTheDocument();
      await waitFor(() => {
        expect(screen.queryByText("No longer playing")).toBeNull();
      });
    });

    it("says a disabled knocked-out player is skipped as a replacement (BR-147)", async () => {
      withoutThirdPlace();
      const out = (await readRounds()).players.find(
        (p) => p.status === "knocked_out",
      );
      await setDisabled(out?.entry_id ?? "");
      const user = userEvent.setup();
      renderAt(knockoutPath());
      await openPlayers(user);

      expect(
        screen.getByText("Not here. Skipped as a replacement."),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", {
          name: `Enable ${nameOf(out?.player_id ?? "")}`,
        }),
      ).toBeInTheDocument();
    });

    it("previews who comes in, skips one who is not here, and draws the plan shown (FR-049, BR-148, BR-155)", async () => {
      withoutThirdPlace();
      await finishNewestRound();
      const before = await readRounds();
      const leaving = before.players.find((p) => p.status === "still_in");
      const [first, second] = before.players.filter(
        (p) => p.status === "knocked_out",
      );
      if (
        leaving === undefined ||
        first === undefined ||
        second === undefined
      ) {
        throw new Error("The knockout has players in and out.");
      }
      await setDisabled(leaving.entry_id);
      const out = nameOf(leaving.player_id);
      const user = userEvent.setup();
      renderAt(knockoutPath());

      expect(await screen.findByText("At this draw:")).toBeInTheDocument();
      expect(
        screen.getByText(`${nameOf(first.player_id)} comes in for ${out}`),
      ).toBeInTheDocument();
      // The plan replaces the general "stays in the draw" notice.
      expect(screen.queryByText(/stays in the draw/)).toBeNull();

      await user.click(
        screen.getByRole("button", {
          name: `${nameOf(first.player_id)} is not here`,
        }),
      );

      expect(
        await screen.findByText(
          `${nameOf(second.player_id)} comes in for ${out}`,
        ),
      ).toBeInTheDocument();
      expect(
        await screen.findByText(
          `${nameOf(first.player_id)} is skipped as a replacement.`,
        ),
      ).toBeInTheDocument();
      await user.click(
        await screen.findByRole("button", { name: "Draw the final" }),
      );

      expect(
        await screen.findByText(`${nameOf(second.player_id)} in for ${out}`),
      ).toBeInTheDocument();
      await openPlayers(user);
      expect(
        screen.getByText(
          `Replaced by ${nameOf(second.player_id)} in the final. Can come back only if you delete that round.`,
        ),
      ).toBeInTheDocument();
    });

    it("says who stays in the draw with nobody to come in (BR-149)", async () => {
      await finishNewestRound();
      const leaving = (await readRounds()).players.find(
        (p) => p.status === "still_in",
      );
      await setDisabled(leaving?.entry_id ?? "");
      const user = userEvent.setup();
      renderAt(knockoutPath());

      expect(
        await screen.findByText(
          `${nameOf(leaving?.player_id ?? "")} has left and nobody can come in, so their pair loses by walkover`,
        ),
      ).toBeInTheDocument();
      expect(screen.queryByText(/stays in the draw/)).toBeNull();
      await openPlayers(user);
      expect(
        screen.getByText(
          "Has left. A replacement comes in at the next draw if anyone can.",
        ),
      ).toBeInTheDocument();
    });

    it("previews a replacement in Czech (FR-049)", async () => {
      await i18n.changeLanguage("cs");
      withoutThirdPlace();
      await finishNewestRound();
      const before = await readRounds();
      const leaving = before.players.find((p) => p.status === "still_in");
      const first = before.players.find((p) => p.status === "knocked_out");
      await setDisabled(leaving?.entry_id ?? "");
      renderAt(knockoutPath());

      expect(
        await screen.findByText(
          `Za hráče ${nameOf(leaving?.player_id ?? "")} nastoupí ${nameOf(first?.player_id ?? "")}`,
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", {
          name: `${nameOf(first?.player_id ?? "")} tu není`,
        }),
      ).toBeInTheDocument();
    });

    it("has no axe violations with the plan and the players shown", async () => {
      withoutThirdPlace();
      await finishNewestRound();
      const leaving = (await readRounds()).players.find(
        (p) => p.status === "still_in",
      );
      await setDisabled(leaving?.entry_id ?? "");
      const user = userEvent.setup();
      renderAt(knockoutPath());
      await screen.findByText("At this draw:");
      await openPlayers(user);

      expect(await violations()).toEqual([]);
    });

    it("says plain statuses once the final's round is drawn, as nobody comes in any more (BR-147, BR-148)", async () => {
      withoutThirdPlace();
      await finishNewestRound();
      await drawRound(2);
      const out = (await readRounds()).players.filter(
        (p) => p.status === "knocked_out",
      );
      expect(out).toHaveLength(4);
      await setDisabled(out[0]?.entry_id ?? "");
      const user = userEvent.setup();
      renderAt(knockoutPath());
      await openPlayers(user);

      expect(screen.getAllByText("Knocked out.")).toHaveLength(3);
      expect(screen.getByText("Not here.")).toBeInTheDocument();
      expect(screen.queryByText(/as a replacement/)).toBeNull();
      expect(screen.queryByText(/next draw/)).toBeNull();
    });

    it("says a final winner who left has left, with no next draw (BR-147)", async () => {
      await finishNewestRound();
      const drawn = await drawRound(2);
      const final = drawn.rounds[1]?.matches.find((m) => m.kind === "standard");
      await enterResult(final?.match_id ?? "", true);
      const winner = final?.sides[0]?.player_ids[0] ?? "";
      const entry = (await readRounds()).players.find(
        (p) => p.player_id === winner,
      );
      await setDisabled(entry?.entry_id ?? "");
      const user = userEvent.setup();
      renderAt(knockoutPath());
      await openPlayers(user);

      expect(screen.getByText("Has left.")).toBeInTheDocument();
      expect(screen.queryByText(/next draw/)).toBeNull();
    });

    /** Holds every disable or enable request until the returned function runs. */
    function holdDisableRequests(): () => void {
      let release = (): void => undefined;
      const gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      server.use(
        http.put(
          "/api/v1/leagues/:leagueId/tournaments/:tournamentId/entries/:entryId/disabled",
          // An empty resolver falls through to the fake API.
          async () => {
            await gate;
          },
        ),
      );
      return release;
    }

    it("takes one change at a time: every row waits while one is saved (FR-044)", async () => {
      const release = holdDisableRequests();
      const user = userEvent.setup();
      renderAt(knockoutPath());
      await openPlayers(user);
      const [first] = screen.getAllByRole("button", { name: /^Disable / });
      if (first === undefined) throw new Error("The list has players.");

      await user.click(first);

      await waitFor(() => {
        for (const button of screen.getAllByRole("button", {
          name: /^(Disable|Enable) /,
        })) {
          expect(button).toBeDisabled();
        }
      });
      release();
      await waitFor(() => {
        for (const button of screen.getAllByRole("button", {
          name: /^(Disable|Enable) /,
        })) {
          expect(button).toBeEnabled();
        }
      });
    });

    it("holds the draw and the not-here buttons while a change is saved (FR-049)", async () => {
      withoutThirdPlace();
      await finishNewestRound();
      const leaving = (await readRounds()).players.find(
        (p) => p.status === "still_in",
      );
      await setDisabled(leaving?.entry_id ?? "");
      const release = holdDisableRequests();
      const user = userEvent.setup();
      renderAt(knockoutPath());
      const draw = await screen.findByRole("button", {
        name: "Draw the final",
      });
      expect(draw).toBeEnabled();
      await openPlayers(user);

      const [first] = screen.getAllByRole("button", { name: /^Disable / });
      if (first === undefined) throw new Error("The list has players.");
      await user.click(first);

      await waitFor(() => {
        expect(draw).toBeDisabled();
      });
      expect(
        screen.getByRole("button", { name: / is not here$/ }),
      ).toBeDisabled();
      release();
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Draw the final" }),
        ).toBeEnabled();
      });
    });

    it("has no Players section once the tournament is finished (FR-044)", async () => {
      await finishNewestRound();
      const drawn = await drawRound(2);
      // The final is best of 3, the third-place match one game.
      for (const match of drawn.rounds[1]?.matches ?? []) {
        await enterResult(match.match_id, match.kind === "standard");
      }
      renderAt(knockoutPath());

      expect(
        await screen.findByText("The knockout is finished"),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Players in the knockout" }),
      ).toBeNull();
    });
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
    const bracket = await api.GET(`${root}/bracket`, {
      params: { path: ids(DYP_EVENING) },
    });
    const semifinal = bracket.data?.rounds[0]?.matches[0];
    renderAt(
      generatePath(paths.knockoutResult, {
        leagueId: TEST_LEAGUE_ID,
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
    const refused = await api.PUT(`${root}/matches/{match_id}/result`, {
      params: {
        path: { ...ids(DYP_EVENING), match_id: semifinal?.match_id ?? "" },
      },
      body: { walkover_winner: null, games: [] },
    });
    expect(refused.response.status).toBe(422);
  });

  it("shows the bracket's seeds in the result sheet, not the setup's (D14)", async () => {
    const bracket = await api.GET(`${root}/bracket`, {
      params: { path: ids(DYP_EVENING) },
    });
    const semifinal = bracket.data?.rounds[0]?.matches[0];
    renderAt(
      generatePath(paths.knockoutResult, {
        leagueId: TEST_LEAGUE_ID,
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
    const bracket = await api.GET(`${root}/bracket`, {
      params: { path: ids(DYP_EVENING) },
    });
    const final = bracket.data?.rounds.at(-1)?.matches[0];
    const [one, two] = final?.sides ?? [];
    const put = (expected: [string, string]) =>
      api.PUT(`${root}/matches/{match_id}/result`, {
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
    const real = await api.GET(`${root}/bracket`, {
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

describe("Finished in Lord have mercy (screen 10, BR-145)", () => {
  /** Per-player place rows, partners sharing a place, as the backend sends them. */
  function lordHaveMercyPlaces(replacedSeventh = false) {
    const tournament = db().tournaments.find((t) => t.id === LHM);
    const singles = (tournament?.entries ?? []).filter(
      (e) => e.player_ids.length === 1,
    );
    const name = (index: number) => {
      const id = singles[index]?.player_ids[0];
      const player = db().players.find((p) => p.id === id);
      return shortName(player?.name ?? "");
    };
    const row = (
      index: number,
      place: number,
      partner: number,
      kind: "won_final" | "lost_final" | "lost_in_round" | "replaced",
    ) => ({
      entry_id: singles[index]?.id ?? "",
      place,
      points_per_player: 10 - place,
      reason: {
        kind,
        round:
          kind === "lost_in_round" || kind === "replaced"
            ? "semifinal"
            : "final",
        score: kind === "won_final" ? [10, 3] : null,
        opponent_entry_id: null,
        partner_entry_id: singles[partner]?.id ?? null,
        group_place: null,
        group_format: null,
      },
    });
    server.use(
      // The fake cannot finish a knockout it did not play, so the detail says so.
      http.get("*/api/v1/leagues/:league/tournaments/:tournament", () =>
        HttpResponse.json({
          ...(tournament === undefined ? {} : tournamentRead(tournament)),
          state: "finished",
        }),
      ),
      http.get("*/api/v1/leagues/:league/tournaments/:tournament/places", () =>
        HttpResponse.json({
          complete: true,
          rows: [
            row(0, 1, 1, "won_final"),
            row(1, 1, 0, "won_final"),
            row(2, 2, 3, "lost_final"),
            row(3, 2, 2, "lost_final"),
            row(4, 3, 5, "lost_in_round"),
            row(5, 3, 4, "lost_in_round"),
            row(6, 3, 7, replacedSeventh ? "replaced" : "lost_in_round"),
            row(7, 3, 6, "lost_in_round"),
          ],
        }),
      ),
    );
    return { name };
  }

  it("Finished: Lord have mercy winners read 'Both get' and name no unknown opponent", async () => {
    const { name } = lordHaveMercyPlaces();
    renderAt(at(paths.finished, LHM));

    const winners = await screen.findByRole("region", { name: "Winners" });
    expect(winners).toHaveTextContent(`${name(0)} / ${name(1)}`);
    expect(within(winners).getAllByText(/ \/ /)).toHaveLength(1);
    expect(winners).toHaveTextContent("Won the final 10:3");
    expect(winners).not.toHaveTextContent("Unknown");
    expect(winners).not.toHaveTextContent("against");
    expect(winners).toHaveTextContent("Both get 9 season points.");
  });

  it("lists partners on one line and does not call two pairs on a place shared (BR-145)", async () => {
    const { name } = lordHaveMercyPlaces();
    renderAt(at(paths.finished, LHM));

    const places = await screen.findByRole("region", { name: "Final places" });
    const rows = within(places).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent(`${name(2)} / ${name(3)}`);
    expect(rows[1]).not.toHaveTextContent("Shared");
    expect(rows[1]).toHaveTextContent("+8 each");
    expect(rows[2]).toHaveTextContent(`${name(4)} / ${name(5)}`);
    expect(rows[2]).toHaveTextContent(`${name(6)} / ${name(7)}`);
    expect(rows[2]).toHaveTextContent("Shared. Lost in the semifinals.");
  });

  it("says a replaced player is placed as knocked out in the round of the seat they took (BR-151)", async () => {
    const { name } = lordHaveMercyPlaces(true);
    renderAt(at(paths.finished, LHM));

    const places = await screen.findByRole("region", { name: "Final places" });
    const third = within(places).getAllByRole("listitem")[2];
    expect(third).toHaveTextContent(`${name(6)} / ${name(7)}`);
    // The place reads by the others' reason; the replaced player has a line.
    expect(third).toHaveTextContent("Shared. Lost in the semifinals.");
    expect(third).toHaveTextContent(
      `${name(6)}: Replaced, placed as knocked out in the semifinals`,
    );
  });

  it("says it in Czech (BR-151)", async () => {
    await i18n.changeLanguage("cs");
    const { name } = lordHaveMercyPlaces(true);
    renderAt(at(paths.finished, LHM));

    expect(
      await screen.findByText(
        `${name(6)}: Nahrazen náhradníkem, umístěn jako při konci v semifinále`,
      ),
    ).toBeInTheDocument();
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

  it("draws the cut line from the knockout's qualifiers when the group phase has none (BR-080)", async () => {
    qualifiersOnTheKnockout(SWISS, 2);
    renderAt(at(paths.betweenRounds, SWISS));

    const table = await screen.findByRole("table", {
      name: "Standings, top 2 go through",
    });
    const rows = within(table).getAllByRole("row");
    // The line falls under the second row of players, after the header.
    expect(rows[2]).toHaveClass("border-b-2");
    expect(rows.filter((row) => row.classList.contains("border-b-2"))).toEqual([
      rows[2],
    ]);
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

  it("says the rounds changed when another device added the round first (ADR-008)", async () => {
    server.use(
      http.post(
        "*/api/v1/leagues/:leagueId/tournaments/:tournamentId/rounds",
        () =>
          HttpResponse.json(
            { code: "round_number_changed", detail: { current_round_no: 4 } },
            { status: 409 },
          ),
      ),
    );
    const user = userEvent.setup();
    renderAt(at(paths.betweenRounds, SWISS));

    await user.click(
      await screen.findByRole("button", { name: "Add round 4" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The rounds changed on another device, so they were reloaded. Check them and try again.",
    );
  });

  // The Swiss fixture stands in for the between-rounds screen that Monster DYP shares.
  it("says how many players another round needs (FR-032, BR-064)", async () => {
    server.use(
      http.post(
        "*/api/v1/leagues/:leagueId/tournaments/:tournamentId/rounds",
        () =>
          HttpResponse.json(
            { code: "not_enough_players", detail: { minimum: 4, given: 3 } },
            { status: 422 },
          ),
      ),
    );
    const user = userEvent.setup();
    renderAt(at(paths.betweenRounds, SWISS));

    await user.click(
      await screen.findByRole("button", { name: "Add round 4" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Another round needs at least 4 players who are not disabled.",
    );
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

/** A Monster DYP of nine in round 1 (two teams of four play, one sits out), the sit-out worth 2 points. */
async function monsterOfNine(): Promise<string> {
  const id = await createDraft({
    type: "monster_dyp",
    group_phase: "monster_dyp",
    sit_out_points: 2,
  });
  await pickPlayers(id, 9);
  await startTournament(id);
  return id;
}

/** Gives every match of the tournament a result, side 1 winning 10 : 3. */
async function playAllMatches(tournamentId: string): Promise<void> {
  const tournament = await tournamentOf(tournamentId);
  for (const match of tournament.rounds.flatMap((round) => round.matches)) {
    const saved = await api.PUT(`${root}/matches/{match_id}/result`, {
      params: {
        path: { ...ids(tournamentId), match_id: match.id },
      },
      body: {
        walkover_winner: null,
        games: [{ winner: "side_1", score_1: 10, score_2: 3 }],
      },
    });
    expect(saved.response.ok).toBe(true);
  }
}

describe("Monster DYP between rounds on the real response shapes (screen 11)", () => {
  it("FR-060, BR-063: names the player behind the sit-out entry id, and scores the sit-out (BR-076)", async () => {
    const id = await monsterOfNine();
    const tournament = await tournamentOf(id);
    const [round] = tournament.rounds;
    // RoundRead.sitting_out holds main entry ids; a side has no entry id.
    expect(round?.sitting_out).toHaveLength(1);
    expect(round?.matches[0]?.sides[0]?.entry_id).toBeNull();
    const sitter = tournament.entries.find(
      (e) => e.id === round?.sitting_out[0],
    );
    const players = await api.GET("/api/v1/leagues/{league_id}/players", {
      params: { path: { league_id: TEST_LEAGUE_ID } },
    });
    const full = players.data?.find(
      (p) => p.id === sitter?.player_ids[0],
    )?.name;
    const [first = "", last = ""] = (full ?? "").split(" ");
    const short = `${first} ${last.charAt(0)}.`;

    renderAt(at(paths.betweenRounds, id));

    expect(await screen.findByText(`Sat out: ${short}`)).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: /^Standings/ });
    const row = within(table)
      .getAllByRole("row")
      .find((r) => within(r).queryByText(short) !== null);
    // Points column: the sit-out is worth 2 (FR-039).
    if (row === undefined) {
      throw new Error("The sitter has a row");
    }
    expect(within(row).getAllByRole("cell")[2]).toHaveTextContent("2");
  });

  it("FR-060, BR-074: lists one row per player, and level players share the place", async () => {
    const id = await monsterOfNine();
    await playAllMatches(id);

    renderAt(at(paths.betweenRounds, id));

    const table = await screen.findByRole("table", { name: /^Standings/ });
    const rows = within(table).getAllByRole("row").slice(1);
    const places = rows.map(
      (row) => within(row).getAllByRole("cell")[0]?.textContent,
    );
    // The four winners share 1st, the sitter (2 points) is 5th, the four losers share 6th.
    expect(places).toEqual(["1", "1", "1", "1", "5", "6", "6", "6", "6"]);
  });

  it("FR-040: finishes without a knockout once the round is complete", async () => {
    const user = userEvent.setup();
    const id = await monsterOfNine();
    await playAllMatches(id);
    renderAt(at(paths.betweenRounds, id));

    await user.click(
      await screen.findByRole("button", { name: "Finish the tournament" }),
    );
    const dialog = await screen.findByRole("alertdialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Finish the tournament" }),
    );

    expect(
      await screen.findByRole("region", { name: "Final places" }),
    ).toBeInTheDocument();
  });

  it("FR-040, ADR-008: says the tournament changed on a 409 tournament_not_in_progress", async () => {
    server.use(
      http.post(
        "*/api/v1/leagues/:leagueId/tournaments/:tournamentId/finish",
        () =>
          HttpResponse.json(
            {
              code: "tournament_not_in_progress",
              detail: { state: "finished" },
            },
            { status: 409 },
          ),
      ),
    );
    const user = userEvent.setup();
    const id = await monsterOfNine();
    await playAllMatches(id);
    renderAt(at(paths.betweenRounds, id));

    await user.click(
      await screen.findByRole("button", { name: "Finish the tournament" }),
    );
    const dialog = await screen.findByRole("alertdialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Finish the tournament" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The tournament changed elsewhere. It was reloaded.",
    );
    expect(
      screen.queryByRole("region", { name: "Final places" }),
    ).not.toBeInTheDocument();
  });

  it("ADR-008: says the rounds changed on a 409 round_number_changed", async () => {
    server.use(
      http.post(
        "*/api/v1/leagues/:leagueId/tournaments/:tournamentId/rounds",
        () =>
          HttpResponse.json(
            { code: "round_number_changed", detail: { current_round_no: 2 } },
            { status: 409 },
          ),
      ),
    );
    const user = userEvent.setup();
    const id = await monsterOfNine();
    await playAllMatches(id);
    renderAt(at(paths.betweenRounds, id));

    await user.click(
      await screen.findByRole("button", { name: "Add round 2" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The rounds changed on another device, so they were reloaded. Check them and try again.",
    );
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

  it("orders players level on points by name in the chosen language (FR-081)", async () => {
    await i18n.changeLanguage("cs");
    // Czech puts Č, Ř, Š and Ž after their base letters and "Ch" after H.
    const czechOrder = [
      "Cyril",
      "Čeněk",
      "Hana",
      "Chalupa",
      "Ivan",
      "Radek",
      "Řehoř",
      "Sára",
      "Šimon",
      "Zora",
      "Žaneta",
    ];
    // New players have no season points, so only their names order them.
    db().players.push(
      ...czechOrder.toReversed().map((name, i) => ({
        id: testId(9100 + i),
        league_id: TEST_LEAGUE_ID,
        name,
        removed_at: null,
      })),
    );
    const user = userEvent.setup();
    renderAt(at(paths.lateAndDisabled, MONSTER));

    await user.click(
      await screen.findByRole("button", { name: "Přidat pozdního hráče" }),
    );
    const sheet = await screen.findByRole("dialog", {
      name: "Přidat pozdního hráče",
    });
    const shown = await within(sheet).findAllByText((text) =>
      czechOrder.includes(text),
    );
    expect(shown.map((name) => name.textContent)).toEqual(czechOrder);
  });

  it.each(["dyp", "doubles"] as const)(
    "offers no late player in a %s Swiss, but still disabling (BR-067)",
    async (type) => {
      const swiss = db().tournaments.find((t) => t.id === SWISS);
      if (swiss) {
        swiss.type = type;
      }
      renderAt(at(paths.lateAndDisabled, SWISS));

      expect(
        await screen.findByText("This tournament takes no late players."),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Add a late player" }),
      ).not.toBeInTheDocument();
      expect(
        (await screen.findAllByRole("button", { name: /^Disable / })).length,
      ).toBeGreaterThan(0);
    },
  );

  it("has no axe violations", async () => {
    renderAt(at(paths.lateAndDisabled, MONSTER));
    await screen.findByRole("heading", { name: "15 players, 14 active" });
    expect(await violations()).toEqual([]);
  });
});

describe("Start the knockout (screen 13)", () => {
  it("offers the four modes, Lord have mercy last (FR-045, BR-084)", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.startKnockout, MONSTER));

    const modes = await screen.findByRole("radiogroup", {
      name: "How are the knockout teams formed?",
    });
    expect(
      within(modes)
        .getAllByRole("radio")
        .map((radio) => radio.parentElement?.textContent ?? ""),
    ).toHaveLength(4);
    for (const name of [
      "Seeded pairs",
      "Singles",
      "A little mercy",
      "Lord have mercy",
    ]) {
      expect(
        within(modes).getByRole("radio", { name: new RegExp(`^${name}`) }),
      ).toBeInTheDocument();
    }
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

  it("keeps Draw the knockout disabled and names the problem when can_start is false (BR-080)", async () => {
    server.use(
      http.get(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/preview",
        () =>
          HttpResponse.json({
            can_start: false,
            problem: { code: "knockout_mode_required", detail: {} },
            draw_counter: 0,
            is_cut_by_lot: false,
            max_qualifiers: 4,
            qualifiers: 4,
            entries: [1, 2, 3, 4].map((seed) => ({
              seed,
              members: [{ entry_id: `e${String(seed)}`, place: seed }],
              decided_by_lot: false,
            })),
            first_round: [
              [1, 4],
              [2, 3],
            ],
            bracket_size: 4,
            locks_round_no: 1,
            skipped_entry_ids: [],
          }),
      ),
    );
    renderAt(at(paths.startKnockout, MONSTER));

    expect(
      await screen.findByText("Pick how the teams are formed."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Draw the knockout" }),
    ).toBeDisabled();
  });

  it("shows one warning, not two, while the last group round is unfinished (BR-080)", async () => {
    const monster = db().tournaments.find((t) => t.id === MONSTER);
    const open = monster?.rounds.at(-1)?.matches[0];
    if (open === undefined) throw new Error("The seed has a group round");
    open.outcome = null;
    server.use(
      http.get(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout/preview",
        () =>
          HttpResponse.json({
            can_start: false,
            problem: { code: "group_phase_not_done", detail: {} },
            draw_counter: 0,
            is_cut_by_lot: false,
            max_qualifiers: 4,
            qualifiers: 4,
            entries: [],
            first_round: [],
            bracket_size: 4,
            locks_round_no: 1,
            skipped_entry_ids: [],
          }),
      ),
    );
    renderAt(at(paths.startKnockout, MONSTER));

    expect(
      await screen.findByText("This tournament is not at this step."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Every group match needs a result before the knockout is drawn.",
      ),
    ).not.toBeInTheDocument();
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

  it("draws the A little mercy pairs again and starts with the new counter (FR-045)", async () => {
    const user = userEvent.setup();
    let sent: { expected_qualifier_ids?: string[] } = {};
    server.use(
      http.put<never, { expected_qualifier_ids: string[] }>(
        "/api/v1/leagues/:leagueId/tournaments/:tournamentId/knockout",
        async ({ request }) => {
          sent = await request.clone().json();
          return undefined;
        },
      ),
    );
    renderAt(at(paths.startKnockout, MONSTER));

    const modes = await screen.findByRole("radiogroup", {
      name: "How are the knockout teams formed?",
    });
    await user.click(
      within(modes).getByRole("radio", { name: /^A little mercy/ }),
    );
    const pairs = async () =>
      within(await screen.findByRole("region", { name: "Preview" }))
        .getAllByRole("listitem")
        .map((row) => row.textContent);
    await waitFor(async () => {
      expect(
        screen.getByRole("button", { name: "Draw again" }),
      ).toBeInTheDocument();
      expect((await pairs()).length).toBeGreaterThan(0);
    });
    const before = await pairs();
    await user.click(screen.getByRole("button", { name: "Draw again" }));
    await waitFor(async () => {
      expect(await pairs()).not.toEqual(before);
    });
    await user.click(screen.getByRole("button", { name: "Draw the knockout" }));
    await waitFor(() => {
      expect(sent).toMatchObject({
        expected_draw_counter: 1,
        mode: "a_little_mercy",
      });
    });
    // Every member of every pair, not only the first (BR-081).
    expect(sent.expected_qualifier_ids).toHaveLength(8);
  });

  it("shows no Draw again for seeded pairs and singles (ruling 2)", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.startKnockout, MONSTER));

    const modes = await screen.findByRole("radiogroup", {
      name: "How are the knockout teams formed?",
    });
    expect(
      screen.queryByRole("button", { name: "Draw again" }),
    ).not.toBeInTheDocument();
    await user.click(within(modes).getByRole("radio", { name: /^Singles/ }));
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Quarterfinals" }),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: "Draw again" }),
    ).not.toBeInTheDocument();
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

    const tournament = await api.GET(root, {
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

    const preview = await api.GET(`${root}/knockout/preview`, {
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
    renderAt(generatePath(paths.seasonStandings, { leagueId: TEST_LEAGUE_ID }));

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
    renderAt(generatePath(paths.seasonStandings, { leagueId: TEST_LEAGUE_ID }));

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
    renderAt(generatePath(paths.seasonStandings, { leagueId: TEST_LEAGUE_ID }));

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
    renderAt(generatePath(paths.seasonStandings, { leagueId: TEST_LEAGUE_ID }));

    expect(
      await screen.findByText(/po 2 dohraných turnajích/),
    ).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    renderAt(generatePath(paths.seasonStandings, { leagueId: TEST_LEAGUE_ID }));
    await screen.findByRole("table", { name: "Season standings" });
    expect(await violations()).toEqual([]);
  });
});
