import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";

import { entryPlayers, type PlayModel, scoreOf, sidesOf } from "./model";
import { useNames } from "./useNames";

type PlayStandingRow = components["schemas"]["PlayStandingRow"];

interface StandingsNotesProps {
  model: PlayModel;
  rows: readonly PlayStandingRow[];
  /** Only the first note, as screen 6 shows. */
  firstOnly?: boolean;
}

/**
 * Says which tie-breaker ranks an entry above the next one level on points
 * (BR-101), e.g. "Anna and Petr are ahead of Jana and Tomáš on head-to-head:
 * they won 10:8 in round 5." Entries that met twice get both results.
 */
export function StandingsNotes({
  model,
  rows,
  firstOnly = false,
}: StandingsNotesProps) {
  const { t } = useTranslation();
  const names = useNames(model);

  const notes = rows.flatMap((row, index) => {
    const next = rows[index + 1];
    if (row.ahead_by === null || next === undefined) {
      return [];
    }
    const values = {
      count: entryPlayers(model, row.entry_id).length,
      a: names.entryFirst(row.entry_id),
      b: names.entryFirst(next.entry_id),
    };
    switch (row.ahead_by) {
      case "head_to_head": {
        const between = [...model.matches.values()].filter(
          (info) =>
            info.phase.kind === "group" &&
            info.match.outcome !== null &&
            info.match.sides.every(
              (side) =>
                side.entry_id === row.entry_id ||
                side.entry_id === next.entry_id,
            ),
        );
        // From this row's side, oldest first; null when one has no score.
        const results = between
          .sort((x, y) => x.round.round_no - y.round.round_no)
          .map((info) => {
            const score = scoreOf(info);
            if (!score) {
              return null;
            }
            const mine = sidesOf(info.match)[0].entry_id === row.entry_id;
            return {
              score: t("roundRobin.score", {
                a: mine ? score[0] : score[1],
                b: mine ? score[1] : score[0],
              }),
              round: info.round.round_no,
            };
          });
        const [first, second] = results;
        if (results.length === 1 && first) {
          return [
            t("roundRobin.notes.headToHeadMatch", {
              ...values,
              score: first.score,
              round: first.round,
            }),
          ];
        }
        // #75 Q35: entries that met twice get both results.
        if (results.length === 2 && first && second) {
          return [
            t("roundRobin.notes.headToHeadMatches", {
              ...values,
              first: first.score,
              firstRound: first.round,
              second: second.score,
              secondRound: second.round,
            }),
          ];
        }
        return [t("roundRobin.notes.headToHead", values)];
      }
      case "game_difference":
        return [t("roundRobin.notes.gameDifference", values)];
      case "score_difference":
        return [t("roundRobin.notes.scoreDifference", values)];
    }
  });

  const shown = firstOnly ? notes.slice(0, 1) : notes;
  if (shown.length === 0) {
    return null;
  }
  return (
    <ul className="space-y-1 text-body-sm text-muted-foreground">
      {shown.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  );
}
