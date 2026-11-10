// Every route path of the app (docs/frontend-style.md §9). Links are built
// from these with generatePath, never by joining strings. The comment on a
// screen is its number in the Figma file's "Tournament lifecycle" page.
export const paths = {
  home: "/",
  login: "/login",
  signUp: "/signup",
  myLeagues: "/leagues",

  league: "/leagues/:leagueId",
  tournaments: "/leagues/:leagueId/tournaments", // 1
  newTournament: "/leagues/:leagueId/tournaments/new", // 2
  seasonStandings: "/leagues/:leagueId/standings",
  players: "/leagues/:leagueId/players",
  leagueSettings: "/leagues/:leagueId/settings",

  tournament: "/leagues/:leagueId/tournaments/:tournamentId", // 6
  setupPlayers: "/leagues/:leagueId/tournaments/:tournamentId/setup/players", // 3
  setupDraw: "/leagues/:leagueId/tournaments/:tournamentId/setup/draw", // 4
  setupReview: "/leagues/:leagueId/tournaments/:tournamentId/setup/review", // 5
  fields: "/leagues/:leagueId/tournaments/:tournamentId/fields", // 6b
  moveMatch:
    "/leagues/:leagueId/tournaments/:tournamentId/fields/move/:matchId", // 6c
  editFields: "/leagues/:leagueId/tournaments/:tournamentId/fields/edit", // 6d
  enterResult:
    "/leagues/:leagueId/tournaments/:tournamentId/matches/:matchId/result", // 7
  bestOfResult:
    "/leagues/:leagueId/tournaments/:tournamentId/matches/:matchId/games", // 7b
  groupPhaseDone: "/leagues/:leagueId/tournaments/:tournamentId/group-done", // 8
  knockout: "/leagues/:leagueId/tournaments/:tournamentId/knockout", // 9
  finished: "/leagues/:leagueId/tournaments/:tournamentId/places", // 10
  betweenRounds: "/leagues/:leagueId/tournaments/:tournamentId/rounds", // 11
  lateAndDisabled: "/leagues/:leagueId/tournaments/:tournamentId/entries", // 12
  startKnockout: "/leagues/:leagueId/tournaments/:tournamentId/knockout/start", // 13

  publicLeague: "/public/:shareToken",
  publicTournament: "/public/:shareToken/tournaments/:tournamentId",
} as const satisfies Record<string, `/${string}`>;
