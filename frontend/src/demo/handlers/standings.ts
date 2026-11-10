// Demo handlers: season standings (FR-022, FR-061). The seasons themselves
// come with the league (handlers/leagues.ts).
import { apiError, route } from "../route";
import { db, seasonStandingsOf } from "../store";

export const standingsHandlers = [
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
