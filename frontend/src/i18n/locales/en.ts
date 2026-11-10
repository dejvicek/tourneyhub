// The English texts are the reference: every other language has the same keys.
export const en = {
  app: {
    name: "TourneyHub",
  },
  language: {
    switchLabel: "Language",
    en: { short: "EN", name: "English" },
    cs: { short: "CS", name: "Čeština" },
  },
  home: {
    title: "Welcome to TourneyHub",
    lead: "Run your group's tournaments and seasons from your phone.",
  },
  notFound: {
    title: "Page not found",
    body: "The page you are looking for does not exist.",
    home: "Back to the home page",
  },
};

export type Messages = typeof en;
