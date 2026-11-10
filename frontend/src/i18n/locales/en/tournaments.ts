// Titles follow the screens of the Figma file's "Tournament lifecycle" page.
export const tournaments = {
  list: {
    title: "Tournaments in the season",
    newTournament: "New tournament",
    empty: "No tournaments in this season yet.",
  },
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
