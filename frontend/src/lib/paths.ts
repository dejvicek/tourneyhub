// Every route path of the app (docs/style/frontend-style.md §9). Links are built
// from these with generatePath, never by joining strings. The comment on a
// screen is its number in the Figma file's "Tournament lifecycle" page.
// An overlay is a nested route that opens a sheet over the screen of its
// parent path (src/components/ResponsiveSheet.tsx).
const tournament = "/leagues/:leagueId/tournaments/:tournamentId";

export const paths = {
  home: "/",
  login: "/login",
  signUp: "/signup",
  changePassword: "/account/password",
  admin: "/admin",
  myLeagues: "/leagues",

  league: "/leagues/:leagueId",
  tournaments: "/leagues/:leagueId/tournaments", // 1
  newTournament: "/leagues/:leagueId/tournaments/new", // 2
  seasonStandings: "/leagues/:leagueId/standings",
  players: "/leagues/:leagueId/players",
  leagueSettings: "/leagues/:leagueId/settings",

  // Redirects to the screen for the tournament's state, phase and format.
  tournament,
  setupPlayers: `${tournament}/setup/players`, // 3
  setupDraw: `${tournament}/setup/draw`, // 4
  setupReview: `${tournament}/setup/review`, // 5
  schedule: `${tournament}/schedule`, // 6
  scheduleResult: `${tournament}/schedule/matches/:matchId`, // overlay 7 or 7b
  fields: `${tournament}/fields`, // 6b
  moveMatch: `${tournament}/fields/move/:matchId`, // overlay 6c
  editFields: `${tournament}/fields/edit`, // overlay 6d
  fieldsResult: `${tournament}/fields/matches/:matchId`, // overlay 7 or 7b
  tournamentStandings: `${tournament}/standings`,
  groupPhaseDone: `${tournament}/group-done`, // 8
  knockout: `${tournament}/knockout`, // 9
  knockoutResult: `${tournament}/knockout/matches/:matchId`, // overlay 7 or 7b
  startKnockout: `${tournament}/knockout/start`, // 13
  finished: `${tournament}/places`, // 10
  betweenRounds: `${tournament}/rounds`, // 11
  roundsResult: `${tournament}/rounds/matches/:matchId`, // overlay 7 or 7b
  lateAndDisabled: `${tournament}/entries`, // 12

  publicLeague: "/public/:shareToken",
  publicTournament: "/public/:shareToken/tournaments/:tournamentId",
} as const satisfies Record<string, `/${string}`>;
