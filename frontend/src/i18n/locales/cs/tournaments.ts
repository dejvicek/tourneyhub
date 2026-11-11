import type { CsMessages, Messages } from "../en";
import { tournamentsSetup } from "./tournamentsSetup";

export const tournaments: CsMessages<Messages["tournaments"]> = {
  // Screens 1-5: the list and the setup steps (src/features/tournaments/setup).
  ...tournamentsSetup,
  header: {
    menu: "Nabídka: jazyk a účet",
    shareLink: "Zkopírovat odkaz na tento turnaj",
    back: "Zpět na turnaje",
    tabs: "Pohledy na turnaj",
  },
  tabs: {
    places: "Pořadí",
    schedule: "Rozpis",
    rounds: "Kola",
    knockout: "Vyřazovací fáze",
    fields: "Hřiště",
    players: "Hráči",
    standings: "Tabulka",
  },
  standings: { title: "Pořadí turnaje" },
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
