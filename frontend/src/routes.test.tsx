import { screen, waitFor } from "@testing-library/react";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { TEST_LEAGUE_ID, TEST_SHARE_TOKEN, testId } from "@/test/fake/ids";
import { createSeed } from "@/test/fake/seed";
import { outsideDb } from "@/test/fake/store";
import { renderAt } from "@/test/renderApp";

const seed = createSeed();
function seeded(name: string) {
  const tournament = seed.tournaments.find((t) => t.name === name);
  if (tournament === undefined) {
    throw new Error(`The seed has no ${name}`);
  }
  return tournament;
}
const running = seeded("Thursday DYP");
const autumn = seeded("Autumn Open DYP");
const setup = seeded("Next Thursday DYP");
const monster = seeded("Monster DYP");
const knockoutRunning = seeded("DYP evening");
const groupDone = seeded("Round robin night");
const monsterMatch = monster.rounds.at(-1)?.matches.at(-1)?.id ?? "";
const runningMatch = running.rounds.at(-1)?.matches.at(-1)?.id ?? "";
const autumnFinal = autumn.rounds.at(-1)?.matches[0]?.id ?? "";

const params = {
  leagueId: TEST_LEAGUE_ID,
  tournamentId: running.id,
  matchId: runningMatch,
  shareToken: TEST_SHARE_TOKEN,
};

type Screen = [
  name: keyof typeof paths,
  en: string,
  cs: string,
  options?: { overlay?: boolean; params?: Partial<typeof params> },
];

// Every screen of the route table with its English and Czech title, so a
// screen developer only fills in the page. An overlay is checked as the
// dialog it opens over its parent screen.
const SCREENS: Screen[] = [
  ["home", "Welcome to TourneyHub", "Vítejte v aplikaci TourneyHub"],
  ["login", "Log in", "Přihlášení"],
  ["signUp", "Sign up", "Registrace"],
  ["changePassword", "Change your password", "Změna hesla"],
  ["admin", "Administration", "Správa"],
  ["myLeagues", "My leagues", "Moje ligy"],
  ["tournaments", "Tournaments", "Turnaje"],
  ["newTournament", "Choose the format", "Zvolte formát"],
  // A screen needs a tournament in the state that has it (TournamentGuard).
  [
    "setupPlayers",
    "Who is playing tonight?",
    "Kdo dnes hraje?",
    { params: { tournamentId: setup.id } },
  ],
  [
    "setupDraw",
    "Draw the pairs",
    "Losování dvojic",
    { params: { tournamentId: setup.id } },
  ],
  [
    "setupReview",
    "Ready to start?",
    "Můžeme začít?",
    { params: { tournamentId: setup.id } },
  ],
  // The running round robin opens on its schedule.
  ["tournament", "Round robin in progress", "Probíhá každý s každým"],
  ["schedule", "Round robin in progress", "Probíhá každý s každým"],
  // The play screens' overlays are titled by what they show (G2).
  ["scheduleResult", "Round 5", "5. kolo", { overlay: true }],
  ["fields", "Fields: now playing and waiting", "Hřiště: hraje se a čeká"],
  [
    "moveMatch",
    "Put this match on a field",
    "Dát zápas na hřiště",
    { overlay: true },
  ],
  ["editFields", "Fields", "Hřiště", { overlay: true }],
  ["fieldsResult", "Round 5", "5. kolo", { overlay: true }],
  ["tournamentStandings", "Tournament standings", "Pořadí turnaje"],
  [
    "groupPhaseDone",
    "Round robin done",
    "Každý s každým skončil",
    { params: { tournamentId: groupDone.id } },
  ],
  [
    "knockout",
    "Knockout",
    "Vyřazovací část",
    { params: { tournamentId: knockoutRunning.id } },
  ],
  // The final of Autumn Open DYP is best of three (7b).
  [
    "knockoutResult",
    "Final",
    "Finále",
    {
      overlay: true,
      params: { tournamentId: autumn.id, matchId: autumnFinal },
    },
  ],
  [
    "startKnockout",
    "Start the knockout",
    "Začít vyřazovací část",
    { params: { tournamentId: monster.id } },
  ],
  ["finished", "Finished", "Dohráno", { params: { tournamentId: autumn.id } }],
  ["betweenRounds", "Rounds", "Kola", { params: { tournamentId: monster.id } }],
  [
    "roundsResult",
    "Enter a result",
    "Zadat výsledek",
    {
      overlay: true,
      params: { tournamentId: monster.id, matchId: monsterMatch },
    },
  ],
  [
    "lateAndDisabled",
    "Players",
    "Hráči",
    { params: { tournamentId: monster.id } },
  ],
  ["seasonStandings", "Season standings", "Pořadí sezóny"],
  ["players", "Players", "Hráči"],
  ["leagueSettings", "League settings", "Nastavení ligy"],
  ["publicLeague", "Thursday Foosball", "Thursday Foosball"],
  ["publicTournament", "Thursday DYP", "Thursday DYP"],
];

/** The login of someone who is signed in goes to My leagues (D33). */
function signOutForLogin(name: keyof typeof paths) {
  if (name === "login") {
    outsideDb().signedInUserId = null;
  }
}

async function findTitle(title: string, overlay = false) {
  // A screen's title can wait for its data, slowly under a full run.
  const wait = { timeout: 3000 };
  return overlay
    ? screen.findByRole("dialog", { name: title }, wait)
    : screen.findByRole("heading", { level: 1, name: title }, wait);
}

describe("the route table", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("has a screen for every path", () => {
    expect(SCREENS.map(([name]) => name).sort()).toEqual(
      Object.keys(paths)
        .filter((name) => name !== "league")
        .sort(),
    );
  });

  it.each(SCREENS)(
    "renders %s with its English title",
    async (name, en, _, options) => {
      signOutForLogin(name);
      renderAt(generatePath(paths[name], { ...params, ...options?.params }));

      expect(await findTitle(en, options?.overlay)).toBeInTheDocument();
    },
  );

  it.each(SCREENS)(
    "renders %s with its Czech title",
    async (name, _, cs, options) => {
      await i18n.changeLanguage("cs");
      signOutForLogin(name);
      renderAt(generatePath(paths[name], { ...params, ...options?.params }));

      expect(await findTitle(cs, options?.overlay)).toBeInTheDocument();
    },
  );

  it("opens a tournament on the screen for its state", async () => {
    const view = renderAt(
      generatePath(paths.tournament, { ...params, tournamentId: autumn.id }),
    );

    expect(await findTitle("Finished")).toBeInTheDocument();
    expect(view.state.location.pathname).toBe(
      generatePath(paths.finished, { ...params, tournamentId: autumn.id }),
    );
  });

  it("opens a league on its tournaments", async () => {
    const view = renderAt(generatePath(paths.league, params));

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Tournaments",
      }),
    ).toBeInTheDocument();
    expect(view.state.location.pathname).toBe(
      generatePath(paths.tournaments, params),
    );
  });

  // The end of a round robin that is still running, the schedule of a
  // tournament in setup, the wizard of a running one (D20, D21).
  it.each([
    ["groupPhaseDone", running.id, "schedule"],
    ["schedule", setup.id, "setupPlayers"],
    ["setupPlayers", running.id, "schedule"],
    ["setupReview", running.id, "schedule"],
    ["knockout", running.id, "schedule"],
  ] as const)(
    "sends %s of a tournament that has no such screen to its own screen",
    async (screen, tournamentId, home) => {
      const view = renderAt(
        generatePath(paths[screen], { ...params, tournamentId }),
      );
      await waitFor(() => {
        expect(view.state.location.pathname).toBe(
          generatePath(paths[home], { ...params, tournamentId }),
        );
      });
    },
  );

  it("shows a not-found page for an unknown tournament (D21)", async () => {
    renderAt(
      generatePath(paths.schedule, { ...params, tournamentId: testId(9999) }),
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: "Page not found" }),
    ).toBeInTheDocument();
  });

  it("shows a not-found page for an unknown league (D07)", async () => {
    renderAt(generatePath(paths.tournaments, { leagueId: testId(9998) }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Page not found" }),
    ).toBeInTheDocument();
  });
});
