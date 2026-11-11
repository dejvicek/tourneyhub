// Demo handlers: results (FR-050–FR-053, FR-094, BR-053, BR-090–BR-095,
// BR-120–BR-124). A result is written whole, every game or the walkover;
// the empty result clears it (ADR-008). Typed from the generated schema and
// answered with the backend's codes (P8); the knockout lock (BR-053) is the
// demo's until the backend has knockouts (P10).
import { knockoutLocked } from "../finalsEngine";
import {
  checkResult,
  findMatch,
  formatOf,
  groupLocked,
  phaseOf,
  writeResult,
} from "../playEngine";
import { apiError, route } from "../route";
import { findLeague, findTournament } from "../store";

export const resultHandlers = [
  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/matches/{match_id}/result",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      const match = t && findMatch(t, params.match_id);
      const phase = t && match && phaseOf(t, match);
      if (!t) {
        return apiError(404, "tournament_not_found", {});
      }
      if (!match || !phase) {
        return apiError(404, "match_not_found", {});
      }
      if (match.sides.some((side) => side.player_ids.length === 0)) {
        return apiError(422, "match_sides_unknown", {});
      }
      if (groupLocked(t, match)) {
        return apiError(422, "validation_failed", {
          rule: "BR-053",
          reason: "results_locked",
        });
      }
      if (knockoutLocked(t, match)) {
        return apiError(422, "validation_failed", {
          rule: "BR-094",
          reason: "results_locked",
        });
      }
      const clearing = body.walkover_winner === null && body.games.length === 0;
      if (!clearing) {
        const refusal = checkResult(
          body,
          formatOf(t, match),
          phase,
          findLeague(t.league_id)?.draws_allowed ?? false,
        );
        if (refusal) {
          return apiError(422, refusal.code, refusal.detail);
        }
      }
      writeResult(t, match, body);
      return match;
    },
  ),
];
