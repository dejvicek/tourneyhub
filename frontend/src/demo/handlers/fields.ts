// Demo handlers: fields (FR-090–FR-094, BR-130–BR-135). The placements come
// with the tournament (GET …/tournaments/{tournament_id}); these writes send
// target states: a placement, a field with the number it expects, a field
// removed by its id (ADR-008, DATA-MODEL §4.6).
import type { ErrorResponse } from "../contract";
import { addField, place, type PlayRefusal, removeField } from "../playEngine";
import { apiError, route } from "../route";
import { findTournament, tournamentRead } from "../store";

const notFound = (tournamentId: string) =>
  apiError(404, "not_found", { tournament_id: tournamentId });

function refused({ status, detail }: PlayRefusal): Response {
  const code: ErrorResponse["code"] =
    status === 422
      ? "validation_failed"
      : status === 404
        ? "not_found"
        : "bad_request";
  return apiError(status, code, detail);
}

export const fieldHandlers = [
  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/placements",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params.tournament_id);
      }
      const refusal = place(t, body);
      return refusal ? refused(refusal) : tournamentRead(t);
    },
  ),

  route(
    "post",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params.tournament_id);
      }
      const result = addField(t, body.number);
      return "status" in result ? refused(result) : result;
    },
    201,
  ),

  route(
    "delete",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields/{field_id}",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params.tournament_id);
      }
      const refusal = removeField(t, params.field_id);
      return refusal ? refused(refusal) : null;
    },
  ),
];
