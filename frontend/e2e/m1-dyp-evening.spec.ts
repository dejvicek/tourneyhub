/* eslint-disable playwright/expect-expect -- the fixme parts have no body yet; each package that enables one writes its assertions */
import { expect, type Page, test } from "@playwright/test";

import {
  accessTokenOf,
  addPlayers,
  type Organizer,
  startTournament,
} from "./support/api";
import { setSignupCode } from "./support/stack";

// Milestone M1 (MVP-GAP P11): the DYP evening of PRD §5.1, driven through the
// real UI against the real backend. The UI carries the flows that matter; the
// API does the bulk setup, such as adding the regulars, to keep the run short.
//
// The parts are tests of one serial group, in the order of the evening, and
// they share one organizer, league and tournament. Today the group reaches a
// started tournament; each later part is a `test.fixme` that names the package
// enabling it. When that package lands, drop the `fixme` and fill the step in.

test.describe.configure({ mode: "serial" });

// 12 players come (§5.1.4): 6 pairs, 5 rounds, 15 matches.
const PLAYERS = [
  "Anna Nováková",
  "Bohumil Dvořák",
  "Cyril Procházka",
  "Dana Horáková",
  "Emil Kučera",
  "Filip Šimek",
  "Gabriela Marková",
  "Hana Veselá",
  "Ivan Beneš",
  "Jitka Králová",
  "Karel Fiala",
  "Lenka Pokorná",
] as const;
const PAIRS = PLAYERS.length / 2;
const ROUNDS = PAIRS - 1;
const MATCHES = (PAIRS * (PAIRS - 1)) / 2;
const FIELDS = 2;

// A new organizer and league each run, so that a database that outlives the
// run (a local stack) does not clash with it.
const run = Date.now().toString(36);
const organizer: Organizer = {
  email: `organizer-${run}@example.test`,
  password: `pw-${crypto.randomUUID()}`,
};
/** A number in a text: the lint rule keeps numbers out of templates. */
const n = (value: number) => String(value);

const LEAGUE_NAME = "Thursday Foosball";

/** What the later parts need from the earlier ones. */
const evening = { leagueId: "", tournamentId: "" };

async function logIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(organizer.email);
  await page.getByLabel("Password", { exact: true }).fill(organizer.password);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page).toHaveURL("/leagues");
}

test("the organizer signs up, sets up the league and starts the DYP", async ({
  page,
  request,
}) => {
  // The CLI on the server, not an HTTP route, sets the code (ADR-007).
  const signupCode = setSignupCode();

  await test.step("the organizer signs up with the code (§5.1.1)", async () => {
    await page.goto("/signup");
    await page.getByLabel("Sign-up code").fill(signupCode);
    await page.getByLabel("Email").fill(organizer.email);
    await page.getByLabel("Your name").fill("Olga Organizer");
    await page.getByLabel("Password", { exact: true }).fill(organizer.password);
    await page.getByRole("button", { name: "Create the account" }).click();

    await expect(page).toHaveURL("/leagues");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "My leagues",
    );
  });

  await test.step("the organizer creates the league (§5.1.2)", async () => {
    await page.getByRole("button", { name: "New league" }).click();
    const dialog = page.getByRole("dialog", { name: "New league" });
    await dialog.getByLabel("League name").fill(LEAGUE_NAME);
    await dialog.getByRole("button", { name: "Create the league" }).click();

    await expect(page).toHaveURL(/\/leagues\/[0-9a-f-]{36}\/tournaments$/);
    evening.leagueId =
      /\/leagues\/([0-9a-f-]{36})\//.exec(page.url())?.[1] ?? "";
    expect(evening.leagueId).not.toBe("");
  });

  await test.step("the league defaults are two fields (§5.1.5)", async () => {
    await page.goto(`/leagues/${evening.leagueId}/settings`);
    await expect(page.getByLabel("Fields", { exact: true })).toHaveValue("1");
    await page.getByRole("button", { name: "More: Fields" }).click();
    await page.getByRole("button", { name: "Save league settings" }).click();
    await expect(page.getByText("League settings saved.")).toBeVisible();
    await expect(page.getByLabel("Fields", { exact: true })).toHaveValue(
      String(FIELDS),
    );
  });

  await test.step("the organizer adds the regulars (§5.1.3)", async () => {
    // One through the form, the rest over the API.
    const [first, ...rest] = PLAYERS;
    await page.goto(`/leagues/${evening.leagueId}/players`);
    await page.getByLabel("Name", { exact: true }).fill(first);
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByText(`${first} is on the list.`)).toBeVisible();

    const token = await accessTokenOf(request, organizer);
    await addPlayers(request, token, evening.leagueId, rest);

    await page.reload();
    await expect(
      page.getByText(`${n(PLAYERS.length)} players`, { exact: true }),
    ).toBeVisible();
  });

  await test.step("the organizer picks a DYP round robin (§5.1.4)", async () => {
    await page.goto(`/leagues/${evening.leagueId}/tournaments/new`);
    await page.getByRole("textbox", { name: "Name" }).fill("DYP evening");
    await page.getByRole("radio", { name: /^DYP/ }).check();
    await page.getByRole("radio", { name: "Round robin" }).check();
    await page.getByRole("button", { name: "Next: pick players" }).click();
    await expect(page).toHaveURL(/\/setup\/players$/);
  });

  await test.step("the organizer picks the 12 players (§5.1.4)", async () => {
    await page.getByRole("button", { name: "Pick all" }).click();
    await expect(
      page.getByRole("heading", {
        name: `${n(PLAYERS.length)} of ${n(PLAYERS.length)} picked`,
      }),
    ).toBeVisible();
    await expect(
      page.getByText(`${n(PLAYERS.length)} players make ${n(PAIRS)} pairs`),
    ).toBeVisible();
    await expect(
      page.getByText(
        `The round robin will have ${n(MATCHES)} matches in ${n(ROUNDS)} rounds.`,
      ),
    ).toBeVisible();
    await page.getByRole("button", { name: "Next: draw pairs" }).click();
    await expect(page).toHaveURL(/\/setup\/draw$/);
  });

  await test.step("the halves and the draw give six pairs (§5.1.4)", async () => {
    const top = page.getByRole("heading", { name: "Top half" });
    const bottom = page.getByRole("heading", { name: "Bottom half" });
    await expect(top).toBeVisible();
    await expect(bottom).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Drawn pairs" }),
    ).toBeVisible();
    await expect(
      page.getByRole("list", { name: "Seed order" }).getByRole("listitem"),
    ).toHaveCount(PAIRS);

    // A new draw is a click away and stays valid.
    await page.getByRole("button", { name: "Draw again" }).click();
    await expect(
      page.getByRole("list", { name: "Seed order" }).getByRole("listitem"),
    ).toHaveCount(PAIRS);
    await page.getByRole("link", { name: "Next: review" }).click();
    await expect(page).toHaveURL(/\/setup\/review$/);
  });

  await test.step("the review shows what will start (§5.1.5)", async () => {
    await expect(
      page.getByRole("heading", { level: 1, name: "Ready to start?" }),
    ).toBeVisible();
    await expect(
      page.getByText(
        `${n(PAIRS)} pairs, drawn from ${n(PLAYERS.length)} players`,
      ),
    ).toBeVisible();
    await expect(page.getByText("Round robin, once")).toBeVisible();
    await expect(page.getByText("Not allowed in this league")).toBeVisible();
  });

  await test.step("generate and start gives the schedule (§5.1.5)", async () => {
    // DEFECT: the review screen's "Generate and start" stays disabled in the
    // real stack. The screen waits for GET .../setup/preview, a provisional
    // route the backend does not serve yet (404; src/features/tournaments/
    // api.ts), so it never enables the button and "Matches" says "Loading…".
    // Until that route exists the test starts the tournament with the
    // request the button sends, then goes on in the UI. The fixme below is
    // the UI click.
    evening.tournamentId =
      /\/tournaments\/([0-9a-f-]{36})\//.exec(page.url())?.[1] ?? "";
    expect(evening.tournamentId).not.toBe("");
    const token = await accessTokenOf(request, organizer);
    await startTournament(
      request,
      token,
      evening.leagueId,
      evening.tournamentId,
    );

    await page.goto(
      `/leagues/${evening.leagueId}/tournaments/${evening.tournamentId}/schedule`,
    );

    await expect(
      page.getByText(`0 of ${n(MATCHES)} matches played`),
    ).toBeVisible();
    for (let round = 1; round <= ROUNDS; round++) {
      await expect(
        page.getByRole("heading", { name: `Round ${n(round)}`, exact: true }),
      ).toBeVisible();
    }
  });

  await test.step("two matches of round 1 are on the fields, the third waits (§5.1.5)", async () => {
    const fields = page.getByRole("region", { name: "On the fields" });
    await expect(fields).toContainText("Field 1");
    await expect(fields).toContainText("Field 2");
    const roundOne = page.getByRole("region", { name: "Round 1", exact: true });
    await expect(roundOne).toContainText("2 on fields, 1 waiting");
    const matches = roundOne.getByRole("listitem");
    await expect(matches).toHaveCount(PAIRS / 2);
    await expect(matches.nth(0)).toContainText("Field 1");
    await expect(matches.nth(1)).toContainText("Field 2");
    await expect(matches.nth(2)).toContainText("Number 1 in line");
  });
});

// The review's button, which the real stack cannot click yet: the screen waits
// for GET .../setup/preview, which the backend does not serve (404), so
// "Generate and start" stays disabled. When the route exists, replace the
// API start in the first test with this click and delete this test.
test.fixme("setup/preview: the review's Generate and start starts the tournament (§5.1.5)", async ({
  page,
}) => {
  await logIn(page);

  await test.step("review shows 15 matches in 5 rounds, and the button starts the tournament", async () => {
    // Expect the "Matches" row to read "15 in 5 rounds, all BO1", the button
    // to be enabled, and a click to open the schedule.
  });
});

test.fixme("P8: the organizer enters the results and the field takes the next match (§5.1.6)", async ({
  page,
}) => {
  await logIn(page);

  await test.step("enter each result; every freed field takes the next waiting match", async () => {
    // Open the schedule, enter the result of each match on a field (screen 7),
    // and assert that the standings and the "played" line move, and that the
    // next waiting match is on the freed field.
  });
});

test.fixme("P9: the fields move the matches, and a third table is added halfway (§5.1.6)", async ({
  page,
}) => {
  await logIn(page);

  await test.step("add Field 3 on the fields screen; a waiting match moves onto it", async () => {
    // Manage fields (6d) adds Field 3; the next waiting match starts on it.
  });
});

test.fixme("P10: the knockout of the top 4 decides the places (§5.1.6, §5.1.7)", async ({
  page,
}) => {
  await logIn(page);

  await test.step("start a knockout for the top 4 without a third-place match, BO3 final", async () => {
    // 1st v 4th and 2nd v 3rd; the bracket advances by itself; the final's
    // result finishes the tournament: places 1, 2, 3 (shared), 5, 6.
  });
});

test.fixme("P10: the season standings add 10, 8, 5 and 5 points (§5.1.7)", async ({
  page,
}) => {
  await logIn(page);

  await test.step("open the season standings; winners 10, runners-up 8, semifinal losers 5 each", async () => {
    // Then 2 points for 5th, 0 for 6th.
  });
});

test.fixme("P11: players open the share link and see the round robin, the bracket and the standings (§5.1.8)", async ({
  browser,
}) => {
  await test.step("copy the share link; open it in a fresh context without a session", async () => {
    const viewer = await browser.newContext({ ignoreHTTPSErrors: true });
    await viewer.close();
  });
});
