// Demo handlers: the share-link views, without an account (FR-070–FR-072).
// Read-only; tournaments in setup answer 404, as if they did not exist. An
// unknown token is 404 share_link_not_found with an empty detail, as the
// backend answers it; the token is never echoed.
import { bracketOf, rankingOf, syncBracket } from "../finalsEngine";
import { publicStandings } from "../playEngine";
import { apiError, route } from "../route";
import type { StoredTournament } from "../seed";
import {
  db,
  placesRead,
  publicLeague,
  publicTournaments,
  seasonStandingsOf,
  sharedLeague,
  tournamentRead,
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

const unknownLink = () => apiError(404, "share_link_not_found", {});

/** A season of the share token's league, or the 404 to answer. */
function sharedSeason(shareToken: string, seasonId: string) {
  const league = sharedLeague(shareToken);
  if (league === undefined) {
    return unknownLink();
  }
  return (
    db().seasons.find(
      (season) => season.id === seasonId && season.league_id === league.id,
    ) ?? apiError(404, "season_not_found", {})
  );
}

export const publicHandlers = [
  route("get", "/api/v1/public/{share_token}", ({ params }) => {
    const league = sharedLeague(params.share_token);
    return league ? publicLeague(league) : unknownLink();
  }),

  route(
    "get",
    "/api/v1/public/{share_token}/seasons/{season_id}/tournaments",
    ({ params }) => {
      const season = sharedSeason(params.share_token, params.season_id);
      return season instanceof Response ? season : publicTournaments(season.id);
    },
  ),

  // P10: the season standings, until the backend serves them.
  route(
    "get",
    "/api/v1/public/{share_token}/seasons/{season_id}/standings",
    ({ params }) => {
      const season = sharedSeason(params.share_token, params.season_id);
      return season instanceof Response ? season : seasonStandingsOf(season.id);
    },
  ),

  route(
    "get",
    "/api/v1/public/{share_token}/tournaments/{tournament_id}",
    ({ params }) => {
      if (sharedLeague(params.share_token) === undefined) {
        return unknownLink();
      }
      const t = visibleTournament(params.share_token, params.tournament_id);
      return t ? tournamentRead(t) : apiError(404, "tournament_not_found", {});
    },
  ),

  route(
    "get",
    "/api/v1/public/{share_token}/tournaments/{tournament_id}/standings",
    ({ params }) => {
      const t = visibleTournament(params.share_token, params.tournament_id);
      return t
        ? publicStandings(t)
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
      return bracketOf(t) ?? apiError(404, "knockout_not_found", {});
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
