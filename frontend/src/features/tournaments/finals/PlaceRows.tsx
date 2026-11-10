import { useTranslation } from "react-i18next";

import type { PlaceData } from "@/features/finals/api";

type PlaceDetail = PlaceData;
type PlaceReason = PlaceData["reason"];

import { usePlaceLabel } from "./usePlaceLabel";

interface PlaceRowsProps {
  rows: readonly PlaceDetail[];
  entryName: (entryId: string) => string;
  /** Whether an entry is a pair (the points are "each"). */
  isPair: (entryId: string) => boolean;
}

/** One line telling why an entry got its place ("Won the final 10:7"). */
function useReasonText() {
  const { t } = useTranslation();
  const placeLabel = usePlaceLabel();
  return (reason: PlaceReason, shared: boolean): string => {
    const score =
      reason.score === null
        ? null
        : `${String(reason.score[0])}:${String(reason.score[1])}`;
    const text = (() => {
      switch (reason.kind) {
        case "won_final":
          return score === null
            ? t("finals.finished.reason.won_final_noscore")
            : t("finals.finished.reason.won_final", { score });
        case "lost_final":
          return t("finals.finished.reason.lost_final");
        case "won_third_place":
          return t("finals.finished.reason.won_third_place");
        case "lost_third_place":
          return t("finals.finished.reason.lost_third_place");
        case "lost_in_round":
          return t("finals.finished.reason.lost_in_round", {
            round: t(
              `finals.roundName.${reason.round ?? "final"}`,
            ).toLowerCase(),
          });
        case "group_place":
          return reason.group_format === "round_robin"
            ? t("finals.finished.reason.group_round_robin", {
                place: placeLabel(reason.group_place ?? 0),
              })
            : t("finals.finished.reason.group_standings", {
                place: placeLabel(reason.group_place ?? 0),
              });
      }
    })();
    return shared ? t("finals.finished.reason.shared", { reason: text }) : text;
  };
}

/** The design's Place row: the place, who has it, why, and the season points. */
export function PlaceRows({ rows, entryName, isPair }: PlaceRowsProps) {
  const { t } = useTranslation();
  const placeLabel = usePlaceLabel();
  const reasonText = useReasonText();
  const places = [...new Set(rows.map((row) => row.place))];
  return (
    <ol className="divide-y divide-border border-t border-b border-border">
      {places.map((place) => {
        const group = rows.filter((row) => row.place === place);
        const first = group[0];
        if (first === undefined) {
          return null;
        }
        const points = first.points_per_player;
        return (
          <li
            key={place}
            className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-start gap-x-3 py-3"
          >
            <span className="font-display text-score-m">
              {placeLabel(place)}
            </span>
            <div className="min-w-0 space-y-1">
              {group.map((row) => (
                <p
                  key={row.entry_id}
                  className="text-body-sm font-bold break-words"
                >
                  {entryName(row.entry_id)}
                </p>
              ))}
              <p className="text-body-sm text-muted-foreground">
                {reasonText(first.reason, group.length > 1)}
              </p>
            </div>
            <span className="text-body-md font-bold text-primary">
              {points === 0
                ? t("finals.finished.pointsNone")
                : isPair(first.entry_id)
                  ? t("finals.finished.pointsEach", { points })
                  : t("finals.finished.pointsOwn", { points })}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
