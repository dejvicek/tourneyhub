// Texts every area shares: the app, the language switch, the home page and
// the pages around the routes.
export const common = {
  app: {
    name: "TourneyHub",
    title: "{{screen}} · TourneyHub",
  },
  language: {
    switchLabel: "Language",
    en: { short: "EN", name: "English" },
    cs: { short: "CS", name: "Čeština" },
  },
  home: {
    title: "Welcome to TourneyHub",
    lead: "Run your group's tournaments and seasons from your phone.",
    myLeagues: "Go to my leagues",
  },
  notFound: {
    title: "Page not found",
    body: "The page you are looking for does not exist.",
    home: "Back to the home page",
  },
  placeholder: {
    screen: "Design screen {{screen}}",
    body: "This screen is a placeholder until it is built.",
  },
  routeError: {
    title: "Something went wrong",
    body: "The page could not be shown. Reload it to try again.",
    notFound: "This page does not exist, or it was deleted.",
    reload: "Reload the page",
  },
  close: "Close",
  loading: "Loading…",
  demo: {
    notice: "Demo mode: the data is made up and starts over when you reload.",
  },
};
