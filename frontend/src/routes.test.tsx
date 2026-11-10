import { screen } from "@testing-library/react";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { DEMO_LEAGUE_ID, DEMO_SHARE_TOKEN, demoId } from "@/demo/ids";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { renderAt } from "@/test/renderApp";

const params = {
  leagueId: DEMO_LEAGUE_ID,
  tournamentId: demoId(400),
  matchId: demoId(401),
  shareToken: DEMO_SHARE_TOKEN,
};

// Every screen of the route table with its English and Czech title, so a
// screen developer only fills in the page.
const SCREENS: [keyof typeof paths, string, string][] = [
  ["home", "Welcome to TourneyHub", "Vítejte v aplikaci TourneyHub"],
  ["login", "Log in", "Přihlášení"],
  ["signUp", "Sign up", "Registrace"],
  ["myLeagues", "My leagues", "Moje ligy"],
  ["tournaments", "Tournaments in the season", "Turnaje sezóny"],
  ["newTournament", "Setup: format", "Příprava: formát"],
  ["setupPlayers", "Setup: who is playing tonight", "Příprava: kdo dnes hraje"],
  ["setupDraw", "Setup: draw the DYP pairs", "Příprava: losování dvojic DYP"],
  ["setupReview", "Setup: review and start", "Příprava: kontrola a start"],
  ["tournament", "Round robin in progress", "Probíhá každý s každým"],
  ["fields", "Fields: now playing and waiting", "Hřiště: hraje se a čeká"],
  ["moveMatch", "Fields: move a match", "Hřiště: přesunout zápas"],
  ["editFields", "Fields: add or remove", "Hřiště: přidat nebo odebrat"],
  ["enterResult", "Enter a result", "Zadat výsledek"],
  [
    "bestOfResult",
    "Best-of results: BO2, BO3, BO5",
    "Výsledky na více her: BO2, BO3, BO5",
  ],
  [
    "groupPhaseDone",
    "Group phase done: knockout or finish",
    "Skupinová fáze skončila: vyřazovací fáze, nebo konec",
  ],
  ["knockout", "Knockout in progress", "Probíhá vyřazovací fáze"],
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
  [
    "lateAndDisabled",
    "Swiss and Monster DYP: late and disabled players",
    "Švýcarský systém a Monster DYP: pozdní a pozastavení hráči",
  ],
  [
    "startKnockout",
    "Monster DYP: start the knockout",
    "Monster DYP: start vyřazovací fáze",
  ],
  ["seasonStandings", "Season standings", "Pořadí sezóny"],
  ["players", "Players", "Hráči"],
  ["leagueSettings", "League settings", "Nastavení ligy"],
  ["publicLeague", "League", "Liga"],
  ["publicTournament", "Tournament", "Turnaj"],
];

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

  it.each(SCREENS)("renders %s with its English title", async (name, en) => {
    renderAt(generatePath(paths[name], params));

    expect(
      await screen.findByRole("heading", { level: 1, name: en }),
    ).toBeInTheDocument();
  });

  it.each(SCREENS)("renders %s with its Czech title", async (name, _, cs) => {
    await i18n.changeLanguage("cs");
    renderAt(generatePath(paths[name], params));

    expect(
      await screen.findByRole("heading", { level: 1, name: cs }),
    ).toBeInTheDocument();
  });

  it("opens a league on its tournaments", async () => {
    const view = renderAt(generatePath(paths.league, params));

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Tournaments in the season",
      }),
    ).toBeInTheDocument();
    expect(view.state.location.pathname).toBe(
      generatePath(paths.tournaments, params),
    );
  });
});
