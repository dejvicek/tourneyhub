import { useTranslation } from "react-i18next";

import type { PlayStandingRow } from "@/demo/contract";

import { entryPlayers, type PlayModel, scoreOf, sidesOf } from "./model";
import { useNames } from "./useNames";

interface StandingsNotesProps {
  model: PlayModel;
  rows: readonly PlayStandingRow[];
  /** Only the first note, as screen 6 shows. */
  firstOnly?: boolean;
}

/**
 * Says which tie-breaker ranks an entry above the next one level on points
 * (BR-101), e.g. "Anna and Petr are ahead of Jana and Tomáš on head-to-head:
 * they won 10:8 in round 5."
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
        const only = between.length === 1 ? between[0] : undefined;
        const score = only ? scoreOf(only) : null;
        if (!only || !score) {
          return [t("roundRobin.notes.headToHead", values)];
        }
        const mine = sidesOf(only.match)[0].entry_id === row.entry_id;
        return [
          t("roundRobin.notes.headToHeadMatch", {
            ...values,
            score: t("roundRobin.score", {
              a: mine ? score[0] : score[1],
              b: mine ? score[1] : score[0],
            }),
            round: only.round.round_no,
          }),
        ];
      }
      case "score_difference":
        return [t("roundRobin.notes.scoreDifference", values)];
      case "game_difference":
        return [t("roundRobin.notes.gameDifference", values)];
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
