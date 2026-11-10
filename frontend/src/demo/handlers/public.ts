// Demo handlers: the share-link views, without an account (FR-070–FR-072).
import { apiError, route } from "../route";
import { db, publicLeague, tournamentRead } from "../store";

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
      const league = db().leagues.find(
        (row) => row.settings.share_token === params.share_token,
      );
      const t = db().tournaments.find(
        (row) =>
          row.id === params.tournament_id &&
          row.league_id === league?.league.id &&
          row.state !== "setup",
      );
      return t
        ? tournamentRead(t)
        : apiError(404, "not_found", { tournament_id: params.tournament_id });
    },
  ),
];
