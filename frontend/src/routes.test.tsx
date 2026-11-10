import { screen } from "@testing-library/react";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { DEMO_LEAGUE_ID, DEMO_SHARE_TOKEN } from "@/demo/ids";
import { createSeed } from "@/demo/seed";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
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
const runningMatch = running.rounds.at(-1)?.matches.at(-1)?.id ?? "";
const autumnFinal = autumn.rounds.at(-1)?.matches[0]?.id ?? "";

const params = {
  leagueId: DEMO_LEAGUE_ID,
  tournamentId: running.id,
  matchId: runningMatch,
  shareToken: DEMO_SHARE_TOKEN,
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
  ["admin", "Admin", "Správa"],
  ["myLeagues", "My leagues", "Moje ligy"],
  ["tournaments", "Tournaments", "Turnaje"],
  ["newTournament", "New tournament", "Nový turnaj"],
  ["setupPlayers", "Who is playing tonight?", "Kdo dnes hraje?"],
  ["setupDraw", "Draw the pairs", "Losování dvojic"],
  ["setupReview", "Ready to start?", "Můžeme začít?"],
  // The running round robin opens on its schedule.
  ["tournament", "Round robin in progress", "Probíhá každý s každým"],
  ["schedule", "Round robin in progress", "Probíhá každý s každým"],
  ["scheduleResult", "Enter a result", "Zadat výsledek", { overlay: true }],
  ["fields", "Fields: now playing and waiting", "Hřiště: hraje se a čeká"],
  [
    "moveMatch",
    "Fields: move a match",
    "Hřiště: přesunout zápas",
    { overlay: true },
  ],
  [
    "editFields",
    "Fields: add or remove",
    "Hřiště: přidat nebo odebrat",
    { overlay: true },
  ],
  ["fieldsResult", "Enter a result", "Zadat výsledek", { overlay: true }],
  ["tournamentStandings", "Tournament standings", "Pořadí turnaje"],
  [
    "groupPhaseDone",
    "Group phase done: knockout or finish",
    "Skupinová fáze skončila: vyřazovací fáze, nebo konec",
  ],
  ["knockout", "Knockout in progress", "Probíhá vyřazovací fáze"],
  // The final of Autumn Open DYP is best of three (7b).
  [
    "knockoutResult",
    "Best-of results: BO2, BO3, BO5",
    "Výsledky na více her: BO2, BO3, BO5",
    {
      overlay: true,
      params: { tournamentId: autumn.id, matchId: autumnFinal },
    },
  ],
  [
    "startKnockout",
    "Monster DYP: start the knockout",
    "Monster DYP: start vyřazovací fáze",
  ],
  [
    "finished",
    "Finished: places and season points",
    "Konec: pořadí a body do sezóny",
  ],
  [
    "betweenRounds",
    "Swiss and Monster DYP: between rounds",
    "Švýcarský systém a Monster DYP: mezi koly",
  ],
  ["roundsResult", "Enter a result", "Zadat výsledek", { overlay: true }],
  [
    "lateAndDisabled",
    "Swiss and Monster DYP: late and disabled players",
    "Švýcarský systém a Monster DYP: pozdní a pozastavení hráči",
  ],
  ["seasonStandings", "Season standings", "Pořadí sezóny"],
  ["players", "Players", "Hráči"],
  ["leagueSettings", "League settings", "Nastavení ligy"],
  ["publicLeague", "League", "Liga"],
  ["publicTournament", "Tournament", "Turnaj"],
];

async function findTitle(title: string, overlay = false) {
  return overlay
    ? screen.findByRole("dialog", { name: title })
    : screen.findByRole("heading", { level: 1, name: title });
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
      renderAt(generatePath(paths[name], { ...params, ...options?.params }));

      expect(await findTitle(en, options?.overlay)).toBeInTheDocument();
    },
  );

  it.each(SCREENS)(
    "renders %s with its Czech title",
    async (name, _, cs, options) => {
      await i18n.changeLanguage("cs");
      renderAt(generatePath(paths[name], { ...params, ...options?.params }));

      expect(await findTitle(cs, options?.overlay)).toBeInTheDocument();
    },
  );

  it("opens a tournament on the screen for its state", async () => {
    const view = renderAt(
      generatePath(paths.tournament, { ...params, tournamentId: autumn.id }),
    );

    expect(
      await findTitle("Finished: places and season points"),
    ).toBeInTheDocument();
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
});
