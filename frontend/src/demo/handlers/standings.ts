// Demo handlers: season standings (FR-022, FR-061). The seasons themselves
// come with the league (handlers/leagues.ts).
import { seasonStandings } from "../engine";
import { apiError, route } from "../route";
import {
  db,
  findTournament,
  seasonStandingsOf,
  tournamentRead,
} from "../store";

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

  // finals: what a tournament changed in the season standings (screen 10,
  // BR-110–BR-113). The standings before are those of the other finished
  // tournaments of the season.
  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/season-effect",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return apiError(404, "not_found", {
          tournament_id: params.tournament_id,
        });
      }
      const earnedBy = new Map<string, number>();
      const places = tournamentRead(t).places ?? [];
      for (const row of places) {
        const entry = t.entries.find((e) => e.id === row.entry_id);
        for (const player of entry?.player_ids ?? []) {
          earnedBy.set(player, row.points_per_player);
        }
      }
      const others = db().tournaments.filter(
        (other) =>
          other.season_id === t.season_id &&
          other.state === "finished" &&
          other.id !== t.id,
      );
      const before = new Map(
        seasonStandings(
          others.map((other) => ({
            places: tournamentRead(other).places ?? [],
            members: new Map(other.entries.map((e) => [e.id, e.player_ids])),
          })),
        ).map((row) => [row.player_id, row.place]),
      );
      return seasonStandingsOf(t.season_id).map((row) => ({
        player_id: row.player_id,
        place: row.place,
        points: row.points,
        earned: earnedBy.get(row.player_id) ?? 0,
        previous_place: before.get(row.player_id) ?? null,
      }));
    },
  ),
];
