// Fixes from the demo's QA report (tmp/demo/qa/REPORT.md); each test names
// its defect.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { generatePath } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setAccessToken } from "@/api/token";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { DEMO_LEAGUE_ID, demoId } from "@/test/fake/ids";
import { createSeed } from "@/test/fake/seed";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";
import { server } from "@/test/server";
import {
  createDraft,
  pickPlayers,
  startTournament,
} from "@/test/setupTestHelpers";

const seed = createSeed();
const idOf = (name: string) =>
  seed.tournaments.find((t) => t.name === name)?.id ?? "";
const at = (path: string, name: string, extra: Record<string, string> = {}) =>
  generatePath(path, {
    leagueId: DEMO_LEAGUE_ID,
    tournamentId: idOf(name),
    ...extra,
  });

beforeEach(async () => {
  await i18n.changeLanguage("en");
  setAccessToken(null);
});

afterEach(() => {
  server.events.removeAllListeners();
});

describe("wording and numbers", () => {
  it("D16: a singles round robin says players where a pairs one says pairs", async () => {
    renderAt(at(paths.groupPhaseDone, "Round robin night"));
    await screen.findByRole("heading", { level: 1, name: "Round robin done" });

    expect(await screen.findByText("Players that go through")).toBeVisible();
    expect(screen.getByText(/The best players play semifinals/)).toBeVisible();
    expect(screen.queryByText(/pairs/i)).not.toBeInTheDocument();
  });

  it("D17: a DYP's rounds count pairs, a Monster DYP's count players", async () => {
    renderAt(at(paths.betweenRounds, "Monster DYP"));
    expect(await screen.findByText(/, 15 players$/)).toBeVisible();
  });

  it("D27: the cut line skips a disabled player", async () => {
    renderAt(at(paths.betweenRounds, "Monster DYP"));
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    // The 8th place is disabled and doesn't go through: the line falls
    // under the next active player, the 9th.
    const cut = rows.filter((row) =>
      row.className.includes("border-b-primary"),
    );
    expect(cut).toHaveLength(1);
    expect(cut[0]).toHaveTextContent(/^9/);
    expect(within(rows[8] ?? table).getByText("Disabled")).toBeInTheDocument();
  });

  it("D22: Czech counts wins and losses with the right plural", async () => {
    await i18n.changeLanguage("cs");
    renderAt(at(paths.groupPhaseDone, "Round robin night"));
    const table = await screen.findByRole("table");

    const text = table.textContent;
    expect(text).toMatch(/\b1 výhra\b/);
    expect(text).toMatch(/\b[2-4] výhry\b/);
    expect(text).toMatch(/\b1 prohra\b/);
    expect(text).toMatch(/\b[2-4] prohry\b/);
    expect(text).not.toMatch(/\b[1-4] (výher|proher)\b/);
  });

  it("D23: Czech keeps names in the nominative and has one word for a field", async () => {
    await i18n.changeLanguage("cs");
    const { cs } = await import("@/i18n/locales/cs");
    const all = JSON.stringify(cs);
    expect(all).not.toMatch(/\(a\)/);
    expect(all).not.toMatch(/Hrací pole|hracích polí|stůl|stole/);
    expect(all).not.toMatch(/Čeká na \{\{names\}\}/);
    expect(all).not.toMatch(/před \{\{b\}\}/);
  });
});

describe("D29: the schedule names the pair that sits out", () => {
  it("names who sits out in a round", async () => {
    // 14 players make 7 pairs: one pair sits out each round.
    const id = await createDraft({});
    await pickPlayers(id, 14);
    await startTournament(id);
    renderAt(
      generatePath(paths.schedule, {
        leagueId: DEMO_LEAGUE_ID,
        tournamentId: id,
      }),
    );

    const notes = await screen.findAllByText(/^Sits out this round: /);
    expect(notes[0]).toHaveTextContent(/: \S.* & \S/);
  });
});

describe("D24, D25: the tournament header", () => {
  it("on a phone, has the share link and a menu with the language and the account", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.schedule, "Thursday DYP"));

    await waitFor(() => {
      expect(
        screen.getByRole("button", {
          name: "Copy this tournament's share link",
        }),
      ).toBeEnabled();
    });
    await user.click(
      screen.getByRole("button", { name: "Menu: language and account" }),
    );
    const menu = await screen.findByRole("menu");
    expect(
      within(menu).getByRole("menuitemradio", { name: "English" }),
    ).toBeChecked();
    await user.click(
      within(menu).getByRole("menuitemradio", { name: "Čeština" }),
    );
    expect(
      await screen.findByRole("button", { name: "Nabídka: jazyk a účet" }),
    ).toBeInTheDocument();
    expect(i18n.resolvedLanguage).toBe("cs");
  });

  it("on a desktop, the league's sidebar carries the language and the account, not the header", async () => {
    stubViewport(1280);
    renderAt(at(paths.schedule, "Thursday DYP"));

    expect(
      await screen.findByRole("button", {
        name: "Copy this tournament's share link",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Menu: language and account" }),
    ).not.toBeInTheDocument();
  });
});

describe("D19: closing the result sheet", () => {
  it("returns focus to the link that opened it", async () => {
    const user = userEvent.setup();
    renderAt(at(paths.schedule, "Thursday DYP"));

    const [opener] = await screen.findAllByRole("link", {
      name: /^Enter result,/,
    });
    opener?.focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(opener).toHaveFocus();
    });
  });
});

describe("D26: switches", () => {
  it("toggles the third-place switch from its label", async () => {
    const user = userEvent.setup();
    renderAt(generatePath(paths.newTournament, { leagueId: DEMO_LEAGUE_ID }));

    await user.click(await screen.findByRole("radio", { name: "None" }));
    const label = await screen.findByText("Third-place match");
    const toggle = screen.getByRole("switch", {
      name: "Third-place match",
    });
    const before = toggle.getAttribute("aria-checked");
    await user.click(label);
    expect(toggle.getAttribute("aria-checked")).not.toBe(before);
  });
});

describe("D28: setup says why Next is off", () => {
  it("explains uneven halves", async () => {
    const user = userEvent.setup();
    const { createDraft, pickPlayers } =
      await import("@/test/setupTestHelpers");
    const id = await createDraft({});
    await pickPlayers(id, 12);
    renderAt(
      generatePath(paths.setupDraw, {
        leagueId: DEMO_LEAGUE_ID,
        tournamentId: id,
      }),
    );
    await user.click(await screen.findByRole("radio", { name: "By hand" }));
    const rows = await screen.findAllByRole("radiogroup", { name: /^1\. / });
    await user.click(
      within(rows[0] ?? document.body).getByRole("radio", { name: "Bottom" }),
    );

    expect(
      await screen.findByText(
        "Next unlocks once both halves have the same number of players.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "The pairs appear once both halves have the same number of players.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Next: review")).toHaveAccessibleDescription(
      /same number of players/,
    );
  });
});

describe("D31, D32: no needless requests", () => {
  it("D31: asks nothing about the session after a logout", async () => {
    const user = userEvent.setup();
    renderAt(paths.myLeagues);
    await user.click(await screen.findByRole("button", { name: /^Account: / }));
    const requests: string[] = [];
    server.events.on("request:start", ({ request }) => {
      requests.push(`${request.method} ${new URL(request.url).pathname}`);
    });
    await user.click(await screen.findByRole("menuitem", { name: "Log out" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Log in" }),
    ).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(requests).toEqual(["POST /api/v1/auth/logout"]);
  });

  it("D32: a deleted tournament isn't fetched again", async () => {
    const user = userEvent.setup();
    const id = idOf("October Singles");
    renderAt(generatePath(paths.tournaments, { leagueId: DEMO_LEAGUE_ID }));
    await user.click(
      await screen.findByRole("button", {
        name: "Actions for October Singles",
      }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: "Delete tournament" }),
    );
    const requests: string[] = [];
    server.events.on("request:start", ({ request }) => {
      requests.push(`${request.method} ${new URL(request.url).pathname}`);
    });
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Delete tournament",
      }),
    );
    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: /October Singles/ }),
      ).not.toBeInTheDocument();
    });
    await new Promise((resolve) => setTimeout(resolve, 300));

    expect(requests.filter((r) => r.startsWith("DELETE"))).toHaveLength(1);
    expect(
      requests.filter((r) => r.startsWith("GET") && r.includes(id)),
    ).toEqual([]);
  });
});

describe("unknown ids", () => {
  it("D07: demoId stays outside the seed", () => {
    expect(seed.tournaments.some((t) => t.id === demoId(9999))).toBe(false);
  });
});
