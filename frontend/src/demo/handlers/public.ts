// Demo handlers: the share-link views, without an account (FR-070–FR-072).
// Read-only; tournaments in setup answer 404, as if they did not exist.
import { bracketOf, rankingOf, syncBracket } from "../finalsEngine";
import { apiError, route } from "../route";
import type { StoredTournament } from "../seed";
import {
  db,
  placesRead,
  publicLeague,
  publicTournamentRead,
  tournamentStandings,
} from "../store";

/** A tournament of the share token's league that viewers may see (FR-070). */
function visibleTournament(
  shareToken: string,
  tournamentId: string,
): StoredTournament | undefined {
  const league = db().leagues.find((row) => row.share_token === shareToken);
  return db().tournaments.find(
    (row) =>
      row.id === tournamentId &&
      row.league_id === league?.id &&
      row.state !== "setup",
  );
}

export const publicHandlers = [
  route("get", "/api/v1/public/{share_token}", ({ params }) => {
    return (
      publicLeague(params.share_token) ??
      apiError(404, "not_found", { share_token: params.share_token })
    );
  }),

  route(
    "get",
    "/api/v1/public/{share_token}/tournaments/{tournament_id}",
    ({ params }) => {
      const t = visibleTournament(params.share_token, params.tournament_id);
      return t
        ? publicTournamentRead(t)
        : apiError(404, "not_found", { tournament_id: params.tournament_id });
    },
  ),

  route(
    "get",
    "/api/v1/public/{share_token}/tournaments/{tournament_id}/standings",
    ({ params }) => {
      const t = visibleTournament(params.share_token, params.tournament_id);
      return t
        ? tournamentStandings(t)
        : apiError(404, "not_found", { tournament_id: params.tournament_id });
    },
  ),

  route(
    "get",
    "/api/v1/public/{share_token}/tournaments/{tournament_id}/bracket",
    ({ params }) => {
      const t = visibleTournament(params.share_token, params.tournament_id);
      if (!t) {
        return apiError(404, "not_found", {
          tournament_id: params.tournament_id,
        });
      }
      syncBracket(t);
      return bracketOf(t) ?? apiError(404, "not_found", { knockout: "none" });
    },
  ),

  route(
    "get",
    "/api/v1/public/{share_token}/tournaments/{tournament_id}/ranking",
    ({ params }) => {
      const t = visibleTournament(params.share_token, params.tournament_id);
      return t
        ? rankingOf(t)
        : apiError(404, "not_found", { tournament_id: params.tournament_id });
    },
  ),

  route(
    "get",
    "/api/v1/public/{share_token}/tournaments/{tournament_id}/places",
    ({ params }) => {
      const t = visibleTournament(params.share_token, params.tournament_id);
      return t
        ? placesRead(t)
        : apiError(404, "not_found", { tournament_id: params.tournament_id });
    },
  ),
];
