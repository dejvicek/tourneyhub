// Demo handlers: the running group phase and its end (FR-040, FR-060,
// FR-092): the play screens' read and finishing after the round robin.
import { groupDone, playRead } from "../playEngine";
import { apiError, route } from "../route";
import { findTournament, tournamentRead } from "../store";

export const playHandlers = [
  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/play",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      return t
        ? playRead(t)
        : apiError(404, "not_found", { tournament_id: params.tournament_id });
    },
  ),

  route(
    "post",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/finish",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return apiError(404, "not_found", {
          tournament_id: params.tournament_id,
        });
      }
      if (t.state !== body.expected_state) {
        // ADR-008: a stale or repeated request reloads instead.
        return apiError(409, "bad_request", { state: t.state });
      }
      // FR-040: the round robin's standings become the places (BR-101).
      if (
        t.phases.some((phase) => phase.kind === "knockout") ||
        !groupDone(t)
      ) {
        return apiError(422, "validation_failed", {
          rule: "FR-040",
          reason: "group_not_done",
        });
      }
      t.state = "finished";
      return tournamentRead(t);
    },
  ),
];
