// Demo handlers: results (FR-050–FR-053, FR-094, BR-090–BR-094, BR-120–BR-124).
import type { MatchRead } from "../contract";
import { fillFields, waitingMatches } from "../engine";
import { apiError, route } from "../route";
import { rules } from "../rules";
import { findTournament } from "../store";

/** demo only, the engine decides: whether a phase needs every game's score (BR-092). */
function scoresRequired(
  format: string,
  scoreDifferenceCounts: boolean,
): boolean {
  switch (rules.gameScoresRequired) {
    case "swiss_and_monster_dyp":
      return format === "swiss" || format === "monster_dyp";
    case "when_score_difference_counts":
      return scoreDifferenceCounts;
  }
}

export const resultHandlers = [
  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/matches/{match_id}/result",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      const round = t?.rounds.find((r) =>
        r.matches.some((m) => m.id === params.match_id),
      );
      const match = round?.matches.find((m) => m.id === params.match_id);
      const phase = t?.phases.find((p) => p.id === round?.phase_id);
      if (!t || !match || !phase) {
        return apiError(404, "not_found", { match_id: params.match_id });
      }
      const walkover = body.walkover_winner !== null;
      if (!walkover && body.games.length === 0) {
        return apiError(422, "validation_failed", { games: "missing" });
      }
      const counts = (phase.tiebreakers ?? []).includes("score_difference");
      if (
        !walkover &&
        scoresRequired(phase.format, counts) &&
        body.games.some((g) => g.score_1 === null || g.score_2 === null)
      ) {
        return apiError(422, "validation_failed", {
          games: "scores_required",
          rule: "BR-092",
        });
      }
      const wins = { side_1: 0, side_2: 0, draw: 0 };
      for (const game of body.games) {
        wins[game.winner] += 1;
      }
      match.is_walkover = walkover;
      match.games = walkover
        ? []
        : body.games.map((game, i) => ({ game_no: i + 1, ...game }));
      match.outcome =
        body.walkover_winner ??
        (wins.side_1 > wins.side_2
          ? "side_1"
          : wins.side_2 > wins.side_1
            ? "side_2"
            : "draw");
      match.result_entered_at = new Date().toISOString();

      // FR-094: the match's field is free and takes the next waiting match.
      const freed = t.fields.map((field) =>
        field.match_id === match.id ? { ...field, match_id: null } : field,
      );
      const matchesById = new Map<string, MatchRead>(
        t.rounds.flatMap((r) => r.matches).map((m) => [m.id, m]),
      );
      t.fields = fillFields(
        freed,
        waitingMatches(t.rounds, freed),
        matchesById,
      );
      return match;
    },
  ),
];
