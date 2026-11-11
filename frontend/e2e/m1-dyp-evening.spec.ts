/* eslint-disable playwright/expect-expect -- the fixme parts have no body yet; each package that enables one writes its assertions */
import { expect, type Locator, type Page, test } from "@playwright/test";

import {
  accessTokenOf,
  addPlayers,
  enterResult,
  type FieldsOf,
  fieldsOf,
  matchesOf,
  type Organizer,
} from "./support/api";
import { setSignupCode } from "./support/stack";

// Milestone M1 (MVP-GAP P11): the DYP evening of PRD §5.1, driven through the
// real UI against the real backend. The UI carries the flows that matter; the
// API does the bulk setup, such as adding the regulars, to keep the run short.
//
// The parts are tests of one serial group, in the order of the evening, and
// they share one organizer, league and tournament. The steps no package
// delivers yet are `test.fixme`s that name the package enabling them. When
// that package lands, drop the `fixme` and fill the step in.

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
const evening = { leagueId: "", tournamentId: "", shareLink: "" };

interface SeasonRow {
  place: number;
  played: number;
  wins: number;
  points: number;
}

/** The body rows of a season standings table: place, player, played, wins, points. */
async function seasonRows(table: Locator): Promise<SeasonRow[]> {
  const rows = await table
    .getByRole("row")
    .filter({ has: table.page().getByRole("cell") })
    .evaluateAll((trs) =>
      trs.map((tr) =>
        // The player's name is a cell on the organizer's table and a row
        // header on the viewer's; either way it is the second child.
        [...tr.children].map((cell) => cell.textContent),
      ),
    );
  return rows.map(([place, , played, wins, points]) => ({
    place: Number.parseInt(place ?? "", 10),
    played: Number(played),
    wins: Number(wins),
    points: Number(points),
  }));
}

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
    evening.tournamentId =
      /\/tournaments\/([0-9a-f-]{36})\//.exec(page.url())?.[1] ?? "";
    expect(evening.tournamentId).not.toBe("");
    await expect(
      page.getByText(`${n(MATCHES)} in ${n(ROUNDS)} rounds, all BO1`),
    ).toBeVisible();
    await page.getByRole("button", { name: "Generate and start" }).click();
    await expect(page).toHaveURL(/\/schedule$/);

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

/** Opens the result sheet of the nth match of the schedule (0-based). */
async function openMatch(page: Page, index: number) {
  const matches = page
    .getByRole("region", { name: /^Round \d$/ })
    .getByRole("listitem");
  await matches.nth(index).getByRole("link").click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

/** Taps the last bead of the first pair, and the other pair's goals if given. */
async function tapScore(page: Page, against?: number) {
  const dialog = page.getByRole("dialog");
  // eslint-disable-next-line playwright/no-raw-locators -- the label wrapping a visually hidden radio has no role or name of its own
  await dialog
    .getByRole("radio", { name: /^10 goals for/ })
    .first()
    // The input is hidden; its label is the bead the thumb taps.
    .locator("xpath=..")
    .click();
  if (against !== undefined) {
    await dialog
      .getByRole("textbox", { name: /^Goals for/ })
      .last()
      .fill(n(against));
  }
}

test("the organizer enters, changes and clears results and the field takes the next match (§5.1.6)", async ({
  page,
}) => {
  await logIn(page);
  const schedule = `/leagues/${evening.leagueId}/tournaments/${evening.tournamentId}/schedule`;
  await page.goto(schedule);
  const fields = page.getByRole("region", { name: "On the fields" });
  const firstField = fields.getByRole("listitem").first();
  const roundOne = page.getByRole("region", { name: "Round 1", exact: true });
  const standings = page.getByRole("table", { name: "Standings" });
  const firstPlayed = firstField.textContent();

  await test.step("a result by three taps: the standings move and the field refills", async () => {
    const before = await firstPlayed;
    await openMatch(page, 0);
    await tapScore(page);
    await page.getByRole("button", { name: "Save result" }).click();

    await expect(
      page.getByText(`1 of ${n(MATCHES)} matches played`),
    ).toBeVisible();
    // Field 1 takes the waiting match of round 1.
    await expect(firstField).not.toHaveText(before ?? "");
    await expect(roundOne.getByRole("listitem").nth(2)).toContainText(
      "Field 1",
    );
    await expect(
      standings.getByText("1 played, 1 won, 0 drawn, 0 lost"),
    ).toHaveCount(1);
    await expect(
      standings.getByText("1 played, 0 won, 0 drawn, 1 lost"),
    ).toHaveCount(1);
  });

  await test.step("the result is changed to a score", async () => {
    await openMatch(page, 0);
    await tapScore(page, 4);
    await page.getByRole("button", { name: "Save result" }).click();
    await expect(roundOne.getByRole("listitem").nth(0)).toContainText("10:4");
    await expect(
      page.getByText(`1 of ${n(MATCHES)} matches played`),
    ).toBeVisible();
  });

  await test.step("a second result is cleared again", async () => {
    await openMatch(page, 1);
    await tapScore(page);
    await page.getByRole("button", { name: "Save result" }).click();
    await expect(
      page.getByText(`2 of ${n(MATCHES)} matches played`),
    ).toBeVisible();

    await openMatch(page, 1);
    await page.getByRole("button", { name: "Clear result" }).click();
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Clear result" })
      .click();
    await expect(
      page.getByText(`1 of ${n(MATCHES)} matches played`),
    ).toBeVisible();
    await expect(roundOne.getByRole("listitem").nth(1)).not.toContainText(
      "10:",
    );
  });
});

/** BR-131 over what the API reads: each player is on one field at most. */
function expectNobodyOnTwoFields({ fields, players }: FieldsOf) {
  const onFields = fields.flatMap((field) =>
    field.match_id === null ? [] : (players.get(field.match_id) ?? []),
  );
  expect(new Set(onFields).size).toBe(onFields.length);
}

/** The first waiting match whose players are on no field, if any (BR-130). */
function nextPlayable({ fields, waiting, players }: FieldsOf) {
  const busy = new Set(
    fields.flatMap((field) =>
      field.match_id === null ? [] : (players.get(field.match_id) ?? []),
    ),
  );
  return (
    waiting.find((matchId) =>
      (players.get(matchId) ?? []).every((player) => !busy.has(player)),
    ) ?? null
  );
}

test("the fields move the matches, and a third table is added halfway (§5.1.6)", async ({
  page,
  request,
}) => {
  await logIn(page);
  const token = await accessTokenOf(request, organizer);
  const state = () =>
    fieldsOf(request, token, evening.leagueId, evening.tournamentId);
  await page.goto(
    `/leagues/${evening.leagueId}/tournaments/${evening.tournamentId}/fields`,
  );
  const fieldCard = (number: number) =>
    page.getByRole("article", { name: `Field ${n(number)}`, exact: true });

  await test.step("add Field 3 on the fields screen; a waiting match moves onto it", async () => {
    const before = await state();
    const next = nextPlayable(before);
    expect(next).not.toBeNull();
    await page.getByRole("link", { name: "Manage fields" }).click();
    const sheet = page.getByRole("dialog", { name: "Fields" });
    await sheet.getByRole("button", { name: /^Add a field/ }).click();
    await expect(sheet.getByText("Field 3 added.")).toBeVisible();
    await sheet.getByRole("button", { name: "Done" }).click();

    await expect(fieldCard(3)).toBeVisible();
    const after = await state();
    expect(after.fields.map((field) => field.number)).toEqual([1, 2, 3]);
    expect(after.fields[2]?.match_id).toBe(next);
    expectNobodyOnTwoFields(after);
  });

  await test.step("the matches of Field 1 and Field 2 swap by hand", async () => {
    const before = await state();
    await fieldCard(1).getByRole("link", { name: /^Move/ }).click();
    const sheet = page.getByRole("dialog", { name: "Move this match" });
    await sheet.getByRole("radio", { name: "Field 2" }).click();
    await sheet.getByRole("button", { name: "Swap with Field 2" }).click();
    await expect(sheet).toBeHidden();

    const after = await state();
    expect(after.fields[0]?.match_id).toBe(before.fields[1]?.match_id);
    expect(after.fields[1]?.match_id).toBe(before.fields[0]?.match_id);
    expectNobodyOnTwoFields(after);
  });

  await test.step("a match goes back to waiting; its field takes another one", async () => {
    const before = await state();
    const sentBack = before.fields[0]?.match_id;
    await fieldCard(1).getByRole("link", { name: /^Move/ }).click();
    const sheet = page.getByRole("dialog", { name: "Move this match" });
    await sheet.getByRole("radio", { name: "Back to waiting" }).click();
    await sheet.getByRole("button", { name: "Move to waiting" }).click();
    await expect(sheet).toBeHidden();

    const after = await state();
    expect(after.waiting).toContain(sentBack);
    expect(after.fields.map((field) => field.match_id)).not.toContain(sentBack);
    expectNobodyOnTwoFields(after);
  });

  await test.step("Field 3 is removed; its match waits first", async () => {
    const before = await state();
    const onThree = before.fields[2]?.match_id ?? null;
    expect(onThree).not.toBeNull();
    await page.getByRole("link", { name: "Manage fields" }).click();
    const sheet = page.getByRole("dialog", { name: "Fields" });
    await sheet.getByRole("button", { name: "Remove Field 3" }).click();
    await page
      .getByRole("alertdialog", { name: "Remove Field 3?" })
      .getByRole("button", { name: "Remove Field 3" })
      .click();
    await expect(sheet.getByText("Field 3 removed.")).toBeVisible();
    await sheet.getByRole("button", { name: "Done" }).click();

    const after = await state();
    expect(after.fields.map((field) => field.number)).toEqual([1, 2]);
    // It waits first, or has taken a field that was free at once (BR-132).
    const placed = after.fields.some((field) => field.match_id === onThree);
    expect(placed ? onThree : after.waiting[0]).toBe(onThree);
    expectNobodyOnTwoFields(after);
  });

  await test.step("the other matches over the API, to keep the run short", async () => {
    const matches = await matchesOf(
      request,
      token,
      evening.leagueId,
      evening.tournamentId,
    );
    expect(matches).toHaveLength(MATCHES);
    // The first match keeps its score from the UI.
    for (const [index, match] of matches.slice(1).entries()) {
      await enterResult(
        request,
        token,
        evening.leagueId,
        evening.tournamentId,
        match.id,
        {
          goals: 10,
          against: (index + 1) % 10,
        },
      );
    }
    await page.goto(
      `/leagues/${evening.leagueId}/tournaments/${evening.tournamentId}/schedule`,
    );
    await expect(
      page.getByText(`${n(MATCHES)} of ${n(MATCHES)} matches played`),
    ).toBeVisible();
  });
});

test("the group is done and the organizer finishes: places with season points (§5.1.7)", async ({
  page,
}) => {
  await logIn(page);
  await page.goto(
    `/leagues/${evening.leagueId}/tournaments/${evening.tournamentId}/schedule`,
  );

  await test.step("the round robin is played", async () => {
    await page
      .getByRole("link", {
        name: "See the final standings and what comes next",
      })
      .click();
    await expect(
      page.getByRole("heading", { level: 1, name: "Round robin done" }),
    ).toBeVisible();
    await expect(
      page.getByRole("table", { name: "Final standings" }),
    ).toBeVisible();
  });

  await test.step("finishing the tournament now asks first", async () => {
    await page
      .getByRole("radio", { name: /^Finish the tournament now/ })
      .check();
    await page.getByRole("button", { name: "Finish the tournament" }).click();
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Finish the tournament" })
      .click();
    await expect(page).toHaveURL(/\/places$/);
  });

  await test.step("the places carry the season points of the league's table", async () => {
    await expect(
      page.getByRole("heading", { level: 1, name: "Finished" }),
    ).toBeVisible();
    const places = page.getByRole("region", { name: "Final places" });
    await expect(places.getByRole("listitem")).toHaveCount(PAIRS);
    await expect(page.getByText("Both get 10 season points.")).toBeVisible();
    await expect(places.getByText("+10 each")).toBeVisible();
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

test("the season standings add the tournament's points (§5.1.7)", async ({
  page,
}) => {
  await logIn(page);
  await page.goto(`/leagues/${evening.leagueId}/standings`);

  await test.step("every player of the finished tournament is on the table", async () => {
    await expect(
      page.getByRole("heading", { level: 1, name: "Season standings" }),
    ).toBeVisible();
    await expect(
      page.getByText("after 1 finished tournament", { exact: false }),
    ).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    const rows = await seasonRows(page.getByRole("table"));
    expect(rows).toHaveLength(PLAYERS.length);
    // Both players of a pair get the entry's points (BR-100): the winning pair
    // 10 each (the places screen above), nobody more.
    expect(rows.slice(0, 2)).toEqual([
      expect.objectContaining({ place: 1, played: 1, wins: 1, points: 10 }),
      expect.objectContaining({ place: 1, played: 1, wins: 1, points: 10 }),
    ]);
    expect(rows.every((row) => row.played === 1)).toBe(true);
    expect(rows.reduce((sum, row) => sum + row.wins, 0)).toBe(2);
    const points = rows.map((row) => row.points);
    expect(points).toEqual([...points].sort((a, b) => b - a));
  });

  await test.step("the tournament counts, and links to its places", async () => {
    await page.getByRole("link", { name: /DYP evening/ }).click();
    await expect(page).toHaveURL(/\/places$/);
  });
});

test.describe("the share link (§5.1.8)", () => {
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("players open the shared link without a session and see the league and the tournament", async ({
    page,
    browser,
  }) => {
    await logIn(page);
    await page.goto(
      `/leagues/${evening.leagueId}/tournaments/${evening.tournamentId}/places`,
    );
    await page.getByRole("button", { name: "Copy share link" }).click();
    await expect(page.getByText("Share link copied")).toBeVisible();
    const link = await page.evaluate(() => navigator.clipboard.readText());
    expect(link).toMatch(/\/public\/[^/]+$/);
    evening.shareLink = link;

    // A fresh context: no cookie, no token in memory.
    const viewer = await browser.newContext({
      ignoreHTTPSErrors: true,
      locale: "en-US",
    });
    try {
      const shared = await viewer.newPage();
      await shared.goto(link);
      await expect(
        shared.getByRole("heading", { level: 1, name: LEAGUE_NAME }),
      ).toBeVisible();
      await expect(
        shared.getByText("Shared league, read-only", { exact: false }),
      ).toBeVisible();
      await expect(
        shared.getByRole("link", { name: /DYP evening/ }),
      ).toBeVisible();

      await shared.getByRole("link", { name: /DYP evening/ }).click();
      await expect(
        shared.getByRole("heading", { level: 1, name: "DYP evening" }),
      ).toBeVisible();
      await expect(
        shared.getByText("Finished", { exact: false }).first(),
      ).toBeVisible();
      // Every match of the round robin with its score. The viewer's standings
      // and places come in the next test.
      const results = shared.getByRole("region", { name: "Results" });
      for (let round = 1; round <= ROUNDS; round++) {
        await expect(
          results.getByRole("region", {
            name: `Round ${n(round)}`,
            exact: true,
          }),
        ).toBeVisible();
      }
      await expect(results.getByRole("listitem")).toHaveCount(MATCHES);
      await expect(results.getByText("10 : 4").first()).toBeVisible();
      await expect(shared).not.toHaveURL(/\/login/);
    } finally {
      await viewer.close();
    }
  });
});

test("the shared view also shows the season standings and the final places (§5.1.8)", async ({
  browser,
}) => {
  expect(evening.shareLink).not.toBe("");
  const viewer = await browser.newContext({
    ignoreHTTPSErrors: true,
    locale: "en-US",
  });
  try {
    const shared = await viewer.newPage();
    const problems: string[] = [];
    shared.on("console", (message) => {
      if (message.type() === "error" || message.type() === "warning") {
        problems.push(`console ${message.type()}: ${message.text()}`);
      }
    });
    shared.on("response", (response) => {
      if (response.status() >= 400) {
        problems.push(`${n(response.status())} ${response.url()}`);
      }
    });

    await test.step("the league page has the season standings", async () => {
      await shared.goto(evening.shareLink);
      const standings = shared.getByRole("region", {
        name: "Season standings",
      });
      await expect(standings.getByRole("table")).toBeVisible();
      const rows = await seasonRows(standings.getByRole("table"));
      expect(rows).toHaveLength(PLAYERS.length);
      expect(rows[0]).toEqual(
        expect.objectContaining({ place: 1, played: 1, wins: 1, points: 10 }),
      );
    });

    await test.step("the tournament page has the standings and the final places", async () => {
      await shared.getByRole("link", { name: /DYP evening/ }).click();
      const places = shared.getByRole("region", { name: "Final places" });
      await expect(places.getByRole("listitem")).toHaveCount(PAIRS);
      await expect(places.getByRole("listitem").first()).toContainText(
        "+10 each",
      );
      const table = shared
        .getByRole("region", { name: "Standings", exact: true })
        .getByRole("table");
      await expect(table.getByRole("row")).toHaveCount(PAIRS + 1);
    });

    expect(problems).toEqual([]);
  } finally {
    await viewer.close();
  }
});
