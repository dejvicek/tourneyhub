import { useTranslation } from "react-i18next";

import type { PlaceData } from "@/features/finals/api";

import { pairPlaces, useGroupName } from "./placePairs";
import { usePlaceLabel } from "./usePlaceLabel";

type PlaceDetail = PlaceData;
type PlaceReason = PlaceData["reason"];

interface PlaceRowsProps {
  rows: readonly PlaceDetail[];
  entryName: (entryId: string) => string;
  /** Whether a row is a pair (the points are "each"). */
  isPair: (row: PlaceDetail) => boolean;
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
          return t(`finals.finished.reason.lostIn.${reason.round ?? "final"}`);
        case "replaced":
          // BR-151: placed as if knocked out in the round of the seat they took.
          return t(
            `finals.finished.reason.replacedIn.${reason.round ?? "final"}`,
          );
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
  const groupName = useGroupName(entryName);
  const groups = pairPlaces(rows);
  const places = [...new Set(groups.map((group) => group.place))];
  return (
    <ol className="divide-y divide-border border-t border-b border-border">
      {places.map((place) => {
        const inPlace = groups.filter((group) => group.place === place);
        const head = inPlace[0];
        if (head === undefined) {
          return null;
        }
        const first = head.first;
        const points = first.points_per_player;
        // BR-151: a replaced player shares the place of the pair whose seat
        // they took, so the place reads by the others' reason and each
        // replaced player gets a line of their own.
        const rowsHere = inPlace.flatMap((group) => group.rows);
        const main =
          rowsHere.find((row) => row.reason.kind !== "replaced") ?? first;
        const replaced = rowsHere.filter(
          (row) => row !== main && row.reason.kind === "replaced",
        );
        return (
          <li
            key={place}
            className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-start gap-x-3 py-3"
          >
            <span className="font-display text-score-m">
              {placeLabel(place)}
            </span>
            <div className="min-w-0 space-y-1">
              {inPlace.map((group) => (
                <p
                  key={group.entryIds.join()}
                  className="text-body-sm font-bold break-words"
                >
                  {groupName(group.entryIds)}
                </p>
              ))}
              <p className="text-body-sm text-muted-foreground">
                {reasonText(main.reason, inPlace.length > 1)}
              </p>
              {replaced.map((row) => (
                <p
                  key={row.entry_id}
                  className="text-body-sm text-muted-foreground"
                >
                  {t("finals.finished.reason.named", {
                    name: entryName(row.entry_id),
                    reason: reasonText(row.reason, false),
                  })}
                </p>
              ))}
            </div>
            <span className="text-body-md font-bold text-primary">
              {points === 0
                ? t("finals.finished.pointsNone")
                : isPair(first) || head.entryIds.length > 1
                  ? t("finals.finished.pointsEach", { points })
                  : t("finals.finished.pointsOwn", { points })}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
