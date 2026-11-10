// Demo handlers: seasons and season standings (FR-020–FR-022, FR-061).
import { apiError, route } from "../route";
import { db, findLeague, seasonStandingsOf, withoutLeague } from "../store";

export const standingsHandlers = [
  route("get", "/api/v1/leagues/{league_id}/seasons", ({ params }) => {
    if (!findLeague(params.league_id)) {
      return apiError(404, "league_not_found", { league_id: params.league_id });
    }
    return db()
      .seasons.filter((season) => season.league_id === params.league_id)
      .map(withoutLeague);
  }),

  route(
    "get",
    "/api/v1/leagues/{league_id}/seasons/{season_id}/standings",
    ({ params }) => {
      const season = db().seasons.find(
        (s) => s.id === params.season_id && s.league_id === params.league_id,
      );
      return season
        ? seasonStandingsOf(season.id)
        : apiError(404, "not_found", { season_id: params.season_id });
    },
  ),
];
