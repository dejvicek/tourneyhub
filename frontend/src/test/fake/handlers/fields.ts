// Fake handlers: fields (FR-090–FR-094, BR-130–BR-135). The placements come
// with the tournament (GET …/tournaments/{tournament_id}); these writes send
// target states: a placement, a field with the number it expects, a field
// removed by its id (ADR-008, DATA-MODEL §4.6).
import { addField, place, type PlayRefusal, removeField } from "../playEngine";
import { apiError, route } from "../route";
import { findTournament, tournamentRead } from "../store";

const notFound = () => apiError(404, "tournament_not_found");

function refused({ status, code, detail }: PlayRefusal): Response {
  return apiError(status, code, detail);
}

export const fieldHandlers = [
  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields/placements",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound();
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
        return notFound();
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
        return notFound();
      }
      const refusal = removeField(t, params.field_id);
      return refusal ? refused(refusal) : null;
    },
  ),
];
