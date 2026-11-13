// Fake handlers: tournaments, their setup and progress (FR-030–FR-048).
import { apiError, route } from "../route";
import {
  applyFormat,
  backToSetup,
  createTournament,
  deleteTournament,
  drawAgain,
  pickedCount,
  preview,
  setHalves,
  setPairs,
  setPlayers,
  setSeeding,
  setSeedOrder,
  setTopPlayers,
  type SetupFailure,
  setupRead,
  start,
} from "../setupEngine";
import {
  activeSeason,
  db,
  findLeague,
  findTournament,
  tournamentRead,
  tournamentSummary,
} from "../store";

export const tournamentHandlers = [
  route(
    "get",
    "/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments",
    ({ params }) =>
      db()
        .tournaments.filter(
          (t) =>
            t.league_id === params.league_id &&
            t.season_id === params.season_id,
        )
        .map((t) =>
          // Setup counts the picked players, who have no entry yet.
          t.state === "setup"
            ? { ...tournamentSummary(t), player_count: pickedCount(t) }
            : tournamentSummary(t),
        ),
  ),

  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      return t ? tournamentRead(t) : notFound(params);
    },
  ),

  // ---------------------------------------------------------- setup
  // Screens 1-5: create, format, players, draws, start (src/test/fake/setupEngine.ts).

  route(
    "post",
    "/api/v1/leagues/{league_id}/tournaments",
    ({ params, body }) => {
      const league = findLeague(params.league_id);
      const season = activeSeason(params.league_id);
      if (!league || !season) {
        return leagueMissing(params.league_id);
      }
      // ADR-008: a repeated create returns the tournament it made, if it is
      // in the active season and of the same type; any other is a 409.
      const existing = db().tournaments.find((t) => t.id === body.id);
      if (existing) {
        return existing.season_id === season.id && existing.type === body.type
          ? setupRead(existing)
          : apiError(409, "tournament_id_taken");
      }
      const created = createTournament(body, league, season.id);
      return "status" in created ? failure(created) : setupRead(created);
    },
    201,
  ),

  route(
    "delete",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      // ADR-008: a repeated delete gets 404, which the screen treats as done.
      return t ? (failure(deleteTournament(t)) ?? null) : notFound(params);
    },
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/format",
    ({ params, body }) =>
      inSetup(params, (t, league) => answer(t, applyFormat(t, body, league))),
  ),

  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      return t ? setupRead(t) : notFound(params);
    },
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/players",
    ({ params, body }) =>
      inSetup(params, (t) => answer(t, setPlayers(t, body.player_ids))),
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/halves",
    ({ params, body }) =>
      inSetup(params, (t) => answer(t, setHalves(t, body.method, body.halves))),
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/pairs",
    ({ params, body }) =>
      inSetup(params, (t) => answer(t, setPairs(t, body.pairs))),
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/top-players",
    ({ params, body }) =>
      inSetup(params, (t) => answer(t, setTopPlayers(t, body.player_ids))),
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/seeding",
    ({ params, body }) =>
      inSetup(params, (t) => answer(t, setSeeding(t, body.method))),
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/seed-order",
    ({ params, body }) =>
      inSetup(params, (t) => answer(t, setSeedOrder(t, body.entry_ids))),
  ),

  route(
    "post",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/draw",
    ({ params, body }) =>
      inSetup(params, (t) =>
        answer(t, drawAgain(t, body.target, body.expected_draw_counter)),
      ),
  ),

  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/preview",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      return t ? preview(t) : notFound(params);
    },
  ),

  route(
    "post",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/start",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params);
      }
      return (
        failure(
          start(t, body.expected_draw_counter, body.expected_seed_order),
        ) ?? tournamentRead(t)
      );
    },
  ),

  route(
    "post",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/back-to-setup",
    ({ params }) => {
      // The body can only expect "in_progress" (BackToSetupWrite).
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params);
      }
      return failure(backToSetup(t)) ?? tournamentRead(t);
    },
  ),
];

interface TournamentParams {
  league_id: string;
  tournament_id: string;
}

const leagueMissing = (leagueId: string) =>
  apiError(404, "league_not_found", { league_id: leagueId });

const notFound = (params: TournamentParams) =>
  findLeague(params.league_id)
    ? apiError(404, "tournament_not_found")
    : leagueMissing(params.league_id);

function failure(result: SetupFailure): Response;
function failure(result: SetupFailure | null): Response | undefined;
function failure(result: SetupFailure | null): Response | undefined {
  return result === null
    ? undefined
    : apiError(result.status, result.code, result.detail);
}

/** Runs a setup write on a tournament that is still in setup. */
function inSetup<T>(
  params: TournamentParams,
  write: (
    t: NonNullable<ReturnType<typeof findTournament>>,
    league: NonNullable<ReturnType<typeof findLeague>>,
  ) => T | Response,
): T | Response {
  const t = findTournament(params.league_id, params.tournament_id);
  const league = findLeague(params.league_id);
  if (!t || !league) {
    return notFound(params);
  }
  return t.state === "setup"
    ? write(t, league)
    : apiError(409, "tournament_not_in_setup", { state: t.state });
}

/** The setup of `t` after a write, or the write's failure. */
function answer(
  t: NonNullable<ReturnType<typeof findTournament>>,
  result: SetupFailure | null,
) {
  return failure(result) ?? setupRead(t);
}
