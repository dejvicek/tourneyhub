import type { Messages } from "../en";

export const tournaments: Messages["tournaments"] = {
  list: {
    title: "Turnaje sezóny",
    newTournament: "Nový turnaj",
    empty: "V této sezóně zatím není žádný turnaj.",
  },
  setupFormat: { title: "Příprava: formát" },
  setupPlayers: { title: "Příprava: kdo dnes hraje" },
  setupDraw: { title: "Příprava: losování dvojic DYP" },
  setupReview: { title: "Příprava: kontrola a start" },
  roundRobin: {
    title: "Probíhá každý s každým",
    screens: "Obrazovky tohoto turnaje",
  },
  groupPhaseDone: {
    title: "Skupinová fáze skončila: vyřazovací fáze, nebo konec",
  },
  knockout: { title: "Probíhá vyřazovací fáze" },
  finished: { title: "Konec: pořadí a body do sezóny" },
  betweenRounds: { title: "Švýcarský systém a Monster DYP: mezi koly" },
  lateAndDisabled: {
    title: "Švýcarský systém a Monster DYP: pozdní a pozastavení hráči",
  },
  startKnockout: { title: "Monster DYP: start vyřazovací fáze" },
  state: {
    setup: "Příprava",
    in_progress: "Probíhá",
    finished: "Skončil",
  },
  knockoutModes: {
    seeded_pairs: "Seeded pairs",
    singles: "Singles",
    a_little_mercy: "A little mercy",
    lord_have_mercy: "Lord have mercy",
  },
};
