// Demo handlers: a league's player list (FR-012, BR-001, BR-002). They follow
// the backend's service (backend/src/tourneyhub/services/players.py).
// BR-002 (no removal of a player picked for an unfinished tournament) follows the backend.
import type { components } from "@/api/schema";
import { newId } from "@/lib/newId";

import { nameProblem, type Problem, validationFailed } from "../outsideErrors";
import { apiError, route } from "../route";
import { isPicked } from "../setupEngine";
import { db, findLeague, tournamentSummary } from "../store";

type PlayerRead = components["schemas"]["PlayerRead"];

/** A league holds at most this many players, removed ones included. */
const MAX_PLAYERS = 500;

/** NFC, then whitespace runs collapsed to one space and the ends trimmed. */
function tidyName(name: string): string {
  return name.normalize("NFC").replace(/\s+/g, " ").trim();
}

/**
 * What the API refuses in a name: control and format characters (zero-width
 * and the like), line and paragraph separators, blank-looking letters, and
 * names outside 1 to 100 characters.
 */
const INVISIBLE = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\u115F\u1160\u3164\uFFA0\u2800]/u;

function nameValidation(name: string): Problem | undefined {
  const loc = ["body", "name"];
  if (INVISIBLE.test(name)) {
    return { loc, type: "invisible_characters" };
  }
  return nameProblem(tidyName(name), loc);
}

/** BR-002: the unfinished tournaments the player is picked for (setup) or plays in. */
function unfinishedTournaments(playerId: string) {
  return db().tournaments.filter(
    (t) =>
      t.state !== "finished" && isPicked(t, playerId),
  );
}

function toRead({ id, name, removed_at }: PlayerRead): PlayerRead {
  return { id, name, removed_at };
}

/** The player that has the name (any case) other than `exceptId`, removed or not. */
function holderOf(leagueId: string, name: string, exceptId?: string) {
  return db().players.find(
    (player) =>
      player.league_id === leagueId &&
      player.id !== exceptId &&
      player.name.toLowerCase() === name.toLowerCase(),
  );
}

function nameTaken(holder: PlayerRead) {
  return apiError(422, "player_name_taken", {
    player_id: holder.id,
    name: holder.name,
    removed: holder.removed_at !== null,
  });
}

function leagueNotFound(leagueId: string) {
  return apiError(404, "league_not_found", { league_id: leagueId });
}

function findPlayer(leagueId: string, playerId: string) {
  return db().players.find(
    (player) => player.league_id === leagueId && player.id === playerId,
  );
}

export const playerHandlers = [
  route("get", "/api/v1/leagues/{league_id}/players", ({ params, url }) => {
    if (!findLeague(params.league_id)) {
      return leagueNotFound(params.league_id);
    }
    const includeRemoved = url.searchParams.get("include_removed") === "true";
    // The store keeps players in the order they were added.
    return db()
      .players.filter(
        (player) =>
          player.league_id === params.league_id &&
          (includeRemoved || player.removed_at === null),
      )
      .map(toRead);
  }),

  // The reason a removal would be refused (BR-002), so the screen can say it
  // before the organizer confirms.
  route(
    "get",
    "/api/v1/leagues/{league_id}/players/{player_id}/tournaments",
    ({ params }) => {
      if (!findLeague(params.league_id)) {
        return leagueNotFound(params.league_id);
      }
      const player = findPlayer(params.league_id, params.player_id);
      return player
        ? unfinishedTournaments(player.id).map(tournamentSummary)
        : apiError(404, "player_not_found", { player_id: params.player_id });
    },
  ),

  route(
    "post",
    "/api/v1/leagues/{league_id}/players",
    ({ params, body }) => {
      if (!findLeague(params.league_id)) {
        return leagueNotFound(params.league_id);
      }
      const problem = nameValidation(body.name);
      if (problem) {
        return validationFailed([problem]);
      }
      const name = tidyName(body.name);
      // BR-001: names are unique in a league, case-insensitively, removed holders too.
      const holder = holderOf(params.league_id, name);
      if (holder) {
        return nameTaken(holder);
      }
      const players = db().players;
      const count = players.filter(
        (player) => player.league_id === params.league_id,
      ).length;
      if (count >= MAX_PLAYERS) {
        return apiError(422, "player_limit_reached", { limit: MAX_PLAYERS });
      }
      const player = {
        id: newId(),
        league_id: params.league_id,
        name,
        removed_at: null,
      };
      players.push(player);
      return toRead(player);
    },
    201,
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/players/{player_id}/name",
    ({ params, body }) => {
      if (!findLeague(params.league_id)) {
        return leagueNotFound(params.league_id);
      }
      const player = findPlayer(params.league_id, params.player_id);
      if (!player) {
        return apiError(404, "player_not_found", {
          player_id: params.player_id,
        });
      }
      const problem = nameValidation(body.name);
      if (problem) {
        return validationFailed([problem]);
      }
      const name = tidyName(body.name);
      // The name is the target state; a removed player can be renamed too.
      if (player.name !== name) {
        const holder = holderOf(params.league_id, name, player.id);
        if (holder) {
          return nameTaken(holder);
        }
        player.name = name;
      }
      return toRead(player);
    },
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/players/{player_id}/removed",
    ({ params, body }) => {
      if (!findLeague(params.league_id)) {
        return leagueNotFound(params.league_id);
      }
      const player = findPlayer(params.league_id, params.player_id);
      if (!player) {
        return apiError(404, "player_not_found", {
          player_id: params.player_id,
        });
      }
      // A strict boolean: "true" or 1 is not accepted.
      const removed: unknown = body.removed;
      if (typeof removed !== "boolean") {
        return apiError(422, "validation_failed", { removed: "not_a_boolean" });
      }
      // BR-002, as the backend answers it.
      if (removed) {
        const tournamentIds = unfinishedTournaments(player.id).map((t) => t.id);
        if (tournamentIds.length > 0) {
          return apiError(422, "player_in_unfinished_tournament", {
            tournament_ids: tournamentIds,
          });
        }
      }
      // The flag is the target state: a repeat keeps the first removed_at.
      if (removed && player.removed_at === null) {
        player.removed_at = new Date().toISOString();
      } else if (!removed) {
        player.removed_at = null;
      }
      return toRead(player);
    },
  ),
];
