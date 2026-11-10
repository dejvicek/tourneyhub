// Demo handlers: a league's player list (FR-012, BR-001, BR-002).
import { apiError, route } from "../route";
import { db, findLeague } from "../store";

export const playerHandlers = [
  route("get", "/api/v1/leagues/{league_id}/players", ({ params }) => {
    if (!findLeague(params.league_id)) {
      return apiError(404, "league_not_found", { league_id: params.league_id });
    }
    return db()
      .players.filter((player) => player.league_id === params.league_id)
      .map(({ id, name, removed_at }) => ({ id, name, removed_at }));
  }),

  route(
    "post",
    "/api/v1/leagues/{league_id}/players",
    ({ params, body }) => {
      if (!findLeague(params.league_id)) {
        return apiError(404, "league_not_found", {
          league_id: params.league_id,
        });
      }
      const players = db().players;
      const name = body.name.trim();
      // BR-001: names are unique in a league, compared case-insensitively.
      const taken = players.find(
        (player) =>
          player.league_id === params.league_id &&
          player.name.toLowerCase() === name.toLowerCase(),
      );
      if (taken?.removed_at === null) {
        return apiError(422, "validation_failed", { name, rule: "BR-001" });
      }
      if (taken) {
        // DATA-MODEL §4.2: re-adding a removed player's name restores them.
        taken.removed_at = null;
        return { id: taken.id, name: taken.name, removed_at: null };
      }
      const player = {
        id: crypto.randomUUID(),
        league_id: params.league_id,
        name,
        removed_at: null,
      };
      players.push(player);
      return { id: player.id, name: player.name, removed_at: null };
    },
    201,
  ),
];
