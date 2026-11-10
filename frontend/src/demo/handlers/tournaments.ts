// Demo handlers: tournaments, their setup and progress (FR-030–FR-048).
import { apiError, route } from "../route";
import {
  db,
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
];
