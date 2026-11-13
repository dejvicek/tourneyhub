import { expect, type Locator, type Page, test } from "@playwright/test";

import {
  accessTokenOf,
  addPlayers,
  createLeague,
  enterResult,
  matchesOf,
  type Organizer,
  playerIdsOf,
  signUp,
  startSinglesSwiss,
} from "./support/api";
import { setSignupCode } from "./support/stack";

// A Swiss evening (P12) on screen 11, between rounds, driven through the real
// UI against the real backend: round 1's results, adding a round, deleting
// it and adding it again (FR-040, FR-042, FR-046, BR-065, BR-066), the
// tie-breakers' order (FR-043, BR-072) and the standings with BH1 and BH2,
// then the share link's standings (FR-070). The API does the setup, which
// the M1 evening already covers through the UI.
//
// The parts are tests of one serial group, in the order of the evening, and
// they share one organizer, league and tournament.

test.describe.configure({ mode: "serial" });

// An odd number, so that one player sits out each round (BR-058).
const PLAYERS = [
  "Alena Říhová",
  "Bořek Malý",
  "Cecílie Vlková",
  "David Sýkora",
  "Eva Zemanová",
] as const;
const MATCHES_PER_ROUND = Math.floor(PLAYERS.length / 2);
const NAME = "Swiss evening";

const run = Date.now().toString(36);
const organizer: Organizer = {
  email: `swiss-${run}@example.test`,
  password: `pw-${crypto.randomUUID()}`,
};
/** A number in a text: the lint rule keeps numbers out of templates. */
const n = (value: number) => String(value);

/** What the later parts need from the earlier ones. */
const evening = { leagueId: "", tournamentId: "", shareLink: "" };

/** The columns the standings show, in order: the tie-breakers follow the points. */
const DEFAULT_COLUMNS = ["Place", "Player", "Pts", "BH1", "BH2", "Diff"];
const REORDERED_COLUMNS = ["Place", "Player", "Pts", "BH1", "Diff", "BH2"];

async function logIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(organizer.email);
  await page.getByLabel("Password", { exact: true }).fill(organizer.password);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page).toHaveURL("/leagues");
}

const betweenRounds = () =>
  `/leagues/${evening.leagueId}/tournaments/${evening.tournamentId}/rounds`;

/** The header cells of a standings table, the visually hidden "Place" too. */
async function columnsOf(table: Locator): Promise<string[]> {
  return table.getByRole("columnheader").allTextContents();
}

/** Each body row's cells: place, player, points and the tie-breakers. */
async function bodyRowsOf(table: Locator): Promise<string[][]> {
  return table
    .getByRole("row")
    .filter({ has: table.page().getByRole("cell") })
    .evaluateAll((trs) =>
      trs.map((tr) => [...tr.children].map((cell) => cell.textContent)),
    );
}

/** The round chips of screen 11: one radio per round. */
function roundChips(page: Page) {
  return page.getByRole("radiogroup", { name: "Round" }).getByRole("radio");
}

test("the organizer's Swiss starts with one player sitting out", async ({
  request,
}) => {
  // The CLI on the server, not an HTTP route, sets the code (ADR-007).
  const token = await signUp(request, setSignupCode(), organizer, "Sára Swiss");
  evening.leagueId = await createLeague(request, token, "Swiss Tuesdays");
  await addPlayers(request, token, evening.leagueId, PLAYERS);
  const ids = await playerIdsOf(request, token, evening.leagueId);
  evening.tournamentId = await startSinglesSwiss(
    request,
    token,
    evening.leagueId,
    { name: NAME, playerIds: PLAYERS.map((name) => ids.get(name) ?? "") },
  );
  const matches = await matchesOf(
    request,
    token,
    evening.leagueId,
    evening.tournamentId,
  );
  expect(matches).toHaveLength(MATCHES_PER_ROUND);
});

test("round 1's results, then round 2 is added, deleted and added again (FR-040, FR-046)", async ({
  page,
  request,
}) => {
  await logIn(page);
  await page.goto(betweenRounds());

  await test.step("screen 11 shows round 1 in progress and who sits out", async () => {
    await expect(
      page.getByRole("heading", { level: 1, name: "Rounds" }),
    ).toBeVisible();
    await expect(roundChips(page)).toHaveCount(1);
    await expect(page.getByText("Round 1 is in progress")).toBeVisible();
    await expect(page.getByText(/^Sat out: /)).toBeVisible();
  });

  await test.step("one result through the result sheet", async () => {
    await page
      .getByRole("link", { name: /^Enter result, / })
      .first()
      .click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    // eslint-disable-next-line playwright/no-raw-locators -- the label wrapping a visually hidden radio has no role or name of its own
    await dialog
      .getByRole("radio", { name: /^10 goals for/ })
      .first()
      // The input is hidden; its label is the bead the thumb taps.
      .locator("xpath=..")
      .click();
    await dialog
      .getByRole("textbox", { name: /^Goals for/ })
      .last()
      .fill("6");
    await dialog.getByRole("button", { name: "Save result" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByText(/^(10 : 6|6 : 10)$/)).toBeVisible();
  });

  await test.step("the other results of round 1 over the API", async () => {
    const token = await accessTokenOf(request, organizer);
    const open = (
      await matchesOf(request, token, evening.leagueId, evening.tournamentId)
    ).filter((match) => match.outcome === null);
    for (const [index, match] of open.entries()) {
      await enterResult(
        request,
        token,
        evening.leagueId,
        evening.tournamentId,
        match.id,
        { goals: 10, against: index + 3 },
      );
    }
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Round 1 is complete" }),
    ).toBeVisible();
  });

  await test.step("round 2 is added with the number the screen expects (ADR-008)", async () => {
    await page.getByRole("button", { name: "Add round 2" }).click();
    await expect(page.getByText("Round 2 is in progress")).toBeVisible();
    await expect(roundChips(page)).toHaveCount(2);
    await expect(
      page
        .getByRole("list", { name: "Matches of round 2" })
        .getByRole("listitem"),
    ).toHaveCount(MATCHES_PER_ROUND);
  });

  await test.step("round 2 is deleted after confirming; round 1 is complete again (BR-066)", async () => {
    await page.getByRole("button", { name: "Delete round 2" }).click();
    await page
      .getByRole("alertdialog", { name: "Delete round 2?" })
      .getByRole("button", { name: "Delete round 2" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Round 1 is complete" }),
    ).toBeVisible();
    await expect(roundChips(page)).toHaveCount(1);
  });

  await test.step("round 2 is added again", async () => {
    await page.getByRole("button", { name: "Add round 2" }).click();
    await expect(page.getByText("Round 2 is in progress")).toBeVisible();
    await expect(roundChips(page)).toHaveCount(2);
  });
});

test("the tie-breakers change order and the standings show BH1 and BH2 (FR-043)", async ({
  page,
}) => {
  await logIn(page);
  await page.goto(betweenRounds());
  const table = page.getByRole("table", { name: /^Standings/ });

  await test.step("the default order: BH1, BH2, then the score difference", async () => {
    await expect(table).toBeVisible();
    expect(await columnsOf(table)).toEqual(DEFAULT_COLUMNS);
    await expect(table.getByRole("row")).toHaveCount(PLAYERS.length + 1);
    // Round 1 has results, so every player has a BH1 and a BH2 (BR-073).
    for (const cells of await bodyRowsOf(table)) {
      expect(cells[3]).toMatch(/^\d+$/);
      expect(cells[4]).toMatch(/^\d+$/);
    }
  });

  await test.step("the score difference moves up before BH2 (BR-072)", async () => {
    await page.getByRole("button", { name: "Change the tie-breakers" }).click();
    const sheet = page.getByRole("dialog", { name: "Tie-breakers" });
    await sheet
      .getByRole("button", { name: "Move Score difference up" })
      .click();
    await sheet.getByRole("button", { name: "Save" }).click();
    await expect(sheet).toBeHidden();

    await expect(
      page.getByText(
        /These decide, in this order: BH1, Score difference, BH2\./,
      ),
    ).toBeVisible();
    await expect(table.getByRole("columnheader").nth(4)).toHaveText("Diff");
    expect(await columnsOf(table)).toEqual(REORDERED_COLUMNS);
  });
});

test.describe("the share link (FR-070)", () => {
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("viewers see the Swiss standings in the organizer's order, without a session", async ({
    page,
    browser,
  }) => {
    await logIn(page);
    await page.goto(betweenRounds());
    await page
      .getByRole("button", { name: "Copy this tournament's share link" })
      .click();
    await expect
      .poll(() => page.evaluate(() => navigator.clipboard.readText()))
      .toMatch(/\/public\/[^/]+\/tournaments\/[0-9a-f-]{36}$/);
    evening.shareLink = await page.evaluate(() =>
      navigator.clipboard.readText(),
    );

    // A fresh context: no cookie, no token in memory.
    const viewer = await browser.newContext({
      ignoreHTTPSErrors: true,
      locale: "en-US",
    });
    try {
      const shared = await viewer.newPage();
      const problems: string[] = [];
      shared.on("response", (response) => {
        if (response.status() >= 400) {
          problems.push(`${n(response.status())} ${response.url()}`);
        }
      });
      await shared.goto(evening.shareLink);
      await expect(
        shared.getByRole("heading", { level: 1, name: NAME }),
      ).toBeVisible();
      const table = shared
        .getByRole("region", { name: "Standings", exact: true })
        .getByRole("table");
      await expect(table.getByRole("row")).toHaveCount(PLAYERS.length + 1);
      expect(await columnsOf(table)).toEqual(REORDERED_COLUMNS);
      for (const cells of await bodyRowsOf(table)) {
        expect(cells[3]).toMatch(/^\d+$/);
      }
      // Round 1's results; round 2 has none yet.
      await expect(
        shared
          .getByRole("region", { name: "Results" })
          .getByRole("region", { name: "Round 1", exact: true })
          .getByRole("listitem"),
      ).toHaveCount(MATCHES_PER_ROUND);
      await expect(shared).not.toHaveURL(/\/login/);
      expect(problems).toEqual([]);
    } finally {
      await viewer.close();
    }
  });
});
