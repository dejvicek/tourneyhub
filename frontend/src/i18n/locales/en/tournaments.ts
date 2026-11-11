// Titles follow the screens of the Figma file's "Tournament lifecycle" page.
import { tournamentsSetup } from "./tournamentsSetup";

export const tournaments = {
  // Screens 1-5: the list and the setup steps (src/features/tournaments/setup).
  ...tournamentsSetup,
  header: {
    menu: "Menu: language and account",
    back: "Back to tournaments",
    tabs: "Views of this tournament",
  },
  tabs: {
    places: "Places",
    schedule: "Schedule",
    rounds: "Rounds",
    knockout: "Knockout",
    fields: "Fields",
    players: "Players",
    standings: "Standings",
  },
  standings: { title: "Tournament standings" },
  setupFormat: { title: "Setup: format" },
  setupPlayers: { title: "Setup: who is playing tonight" },
  setupDraw: { title: "Setup: draw the DYP pairs" },
  setupReview: { title: "Setup: review and start" },
  roundRobin: {
    title: "Round robin in progress",
    screens: "Screens of this tournament",
  },
  groupPhaseDone: { title: "Group phase done: knockout or finish" },
  knockout: { title: "Knockout in progress" },
  finished: { title: "Finished: places and season points" },
  betweenRounds: { title: "Swiss and Monster DYP: between rounds" },
  lateAndDisabled: {
    title: "Swiss and Monster DYP: late and disabled players",
  },
  startKnockout: { title: "Monster DYP: start the knockout" },
  state: {
    setup: "Setup",
    in_progress: "In progress",
    finished: "Finished",
  },
  // FR-080: the same names in every language (src/demo/rules.ts).
  knockoutModes: {
    seeded_pairs: "Seeded pairs",
    singles: "Singles",
    a_little_mercy: "A little mercy",
    lord_have_mercy: "Lord have mercy",
  },
};
