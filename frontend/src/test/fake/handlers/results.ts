// Fake handlers: results (FR-050–FR-053, FR-094, BR-053, BR-090–BR-095,
// BR-120–BR-124). A result is written whole, every game or the walkover;
// the empty result clears it (ADR-008). Typed from the generated schema and
// answered with the backend's codes (P8, P10b).
import { knockoutLocked } from "../finalsEngine";
import {
  checkResult,
  findMatch,
  formatOf,
  groupLocked,
  outcomeOf,
  phaseOf,
  writeResult,
} from "../playEngine";
import { isRemix, remixLocked, remixRounds } from "../remixEngine";
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
      // ADR-008: the entries the screen saw on both sides are still there.
      const [first, second] = match.sides;
      const expected = body.expected_sides;
      if (
        expected &&
        first.entry_id &&
        second.entry_id &&
        (first.entry_id !== expected[0] || second.entry_id !== expected[1])
      ) {
        return apiError(409, "match_sides_changed", {
          entry_ids: [first.entry_id, second.entry_id],
        });
      }
      if (match.sides.some((side) => side.player_ids.length === 0)) {
        return apiError(422, "match_sides_unknown", {});
      }
      if (groupLocked(t, match)) {
        return apiError(422, "group_phase_locked", {});
      }
      const clearing = body.walkover_winner === null && body.games.length === 0;
      if (isRemix(t)) {
        // BR-146: drawing a round locks the winners of the round before.
        if (remixLocked(t, match, clearing ? null : outcomeOf(body))) {
          return apiError(422, "round_locked", {
            round_no: remixRounds(t).length,
          });
        }
      } else if (knockoutLocked(t, match)) {
        return apiError(422, "result_locked", {});
      }
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
