// Demo handlers: tournaments, their setup and progress (FR-030–FR-048).
import { HttpResponse } from "msw";

import type { SetupConflictCode } from "../contract";
import { apiError, route } from "../route";
import {
  applyFormat,
  backToSetup,
  createTournament,
  deleteTournament,
  drawAgain,
  formatProblem,
  leagueRanking,
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
  tournamentStandings,
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
        .map(tournamentSummary),
  ),

  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      return t
        ? tournamentRead(t)
        : apiError(404, "not_found", { tournament_id: params.tournament_id });
    },
  ),

  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/standings",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      return t
        ? tournamentStandings(t)
        : apiError(404, "not_found", { tournament_id: params.tournament_id });
    },
  ),

  // ---------------------------------------------------------- setup
  // Screens 1-5: create, format, players, draws, start (src/demo/setupEngine.ts).

  route("get", "/api/v1/leagues/{league_id}/ranking", ({ params }) =>
    findLeague(params.league_id)
      ? leagueRanking(params.league_id)
      : leagueMissing(params.league_id),
  ),

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
      // the same league and type; any other tournament with that id is a 409.
      const existing = db().tournaments.find((t) => t.id === body.id);
      if (existing) {
        return existing.league_id === params.league_id &&
          existing.type === body.type
          ? tournamentRead(existing)
          : conflict("tournament_id_taken", { id: body.id });
      }
      const problem = formatProblem(body, league.draws_allowed);
      if (problem) {
        return apiError(422, problem.code, problem.detail);
      }
      return tournamentRead(
        createTournament(body.id, params.league_id, season.id, body),
      );
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
      inSetup(params, (t, league) => {
        const problem = formatProblem(body, league.draws_allowed);
        if (problem) {
          return apiError(422, problem.code, problem.detail);
        }
        applyFormat(t, body);
        return tournamentRead(t);
      }),
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
      return failure(start(t, body.expected_draw_counter)) ?? tournamentRead(t);
    },
  ),

  route(
    "post",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/back-to-setup",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params);
      }
      return failure(backToSetup(t, body.expected_state)) ?? tournamentRead(t);
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
  apiError(404, "not_found", { tournament_id: params.tournament_id });

/** A 409 of setup (ADR-008): the screen reloads and shows what changed. */
function conflict(
  code: SetupConflictCode,
  detail: Record<string, string> = {},
) {
  return HttpResponse.json({ code, detail }, { status: 409 });
}

function failure(result: SetupFailure | null): Response | undefined {
  if (result === null) {
    return undefined;
  }
  return result.status === 409
    ? conflict(result.code)
    : apiError(422, result.code, result.detail);
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
    : conflict("tournament_not_in_setup");
}

/** The setup of `t` after a write, or the write's failure. */
function answer(
  t: NonNullable<ReturnType<typeof findTournament>>,
  result: SetupFailure | null,
) {
  return failure(result) ?? setupRead(t);
}
