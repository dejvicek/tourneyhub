import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { cn } from "@/lib/utils";

type ParticipantRead = components["schemas"]["ParticipantRead"];
type Tiebreaker = components["schemas"]["Tiebreaker"];

/**
 * One row of the standings: what both the organizer's GET …/play and the
 * share link's GET …/standings answer.
 */
export type RankingRow = Pick<
  components["schemas"]["PlayStandingRow"],
  "place" | "entry_id" | "points" | "bh1" | "bh2" | "score_difference"
>;

interface RankingTableProps {
  rows: readonly RankingRow[];
  /** The enabled tie-breakers, in the organizer's order (FR-043, BR-072). */
  tiebreakers: readonly Tiebreaker[];
  /** How many go through to the knockout, if the setup said. */
  qualifiers: number | null;
  /** The entries that are disabled (BR-064); they never go through (BR-080). */
  disabled: ReadonlySet<string>;
  participants: readonly ParticipantRead[];
  entryName: (entryId: string) => string;
  /** The table's accessible name, as its heading says it. */
  caption: string;
}

function valueOf(row: RankingRow, key: Tiebreaker) {
  switch (key) {
    case "bh1":
      return row.bh1;
    case "bh2":
      return row.bh2;
    case "score_difference":
      return row.score_difference;
  }
}

/** Swiss and Monster DYP standings: points and the enabled tie-breakers, in their order (FR-043). */
export function RankingTable({
  rows,
  tiebreakers,
  qualifiers,
  disabled,
  participants,
  entryName,
  caption,
}: RankingTableProps) {
  const { t, i18n } = useTranslation();
  const number = new Intl.NumberFormat(i18n.resolvedLanguage, {
    signDisplay: "exceptZero",
  });
  // The line falls after the last player who can go through: disabled
  // players don't, so they don't count towards it (BR-080).
  let cutIndex = -1;
  if (qualifiers !== null) {
    let enabled = 0;
    rows.forEach((row, index) => {
      if (!disabled.has(row.entry_id) && enabled < qualifiers) {
        enabled += 1;
        cutIndex = index;
      }
    });
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-72 border-collapse text-body-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="text-caption text-muted-foreground">
            <th scope="col" className="w-9 py-2 pr-2 text-start font-normal">
              <span className="sr-only">
                {t("finals.rounds.columns.place")}
              </span>
            </th>
            <th scope="col" className="py-2 text-start font-normal">
              {t("finals.rounds.columns.player")}
            </th>
            <th scope="col" className="w-12 py-2 text-end font-normal">
              {t("finals.rounds.columns.points")}
            </th>
            {tiebreakers.map((key) => (
              <th
                key={key}
                scope="col"
                className="w-12 py-2 text-end font-normal"
              >
                {t(`finals.rounds.columns.${key}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const info = participants.find((p) => p.entry_id === row.entry_id);
            const isDisabled = disabled.has(row.entry_id);
            const label = isDisabled
              ? t("finals.rounds.disabledLabel")
              : info?.joined_round != null
                ? t("finals.rounds.joinedLabel", { round: info.joined_round })
                : null;
            return (
              <tr
                key={row.entry_id}
                className={cn(
                  "border-t border-border",
                  index === cutIndex && "border-b-2 border-b-primary",
                )}
              >
                <td className="py-2.5 pr-2 font-display text-score-s">
                  {row.place}
                </td>
                <td className="py-2.5">
                  <span className={cn(isDisabled && "text-muted-foreground")}>
                    {entryName(row.entry_id)}
                  </span>
                  {label !== null && (
                    <span className="block text-caption text-muted-foreground">
                      {label}
                    </span>
                  )}
                </td>
                <td className="py-2.5 text-end font-bold">{row.points}</td>
                {tiebreakers.map((key) => {
                  // BH1 and BH2 are null where the format has none.
                  const value = valueOf(row, key);
                  return (
                    <td key={key} className="py-2.5 text-end">
                      {value === null
                        ? null
                        : key === "score_difference"
                          ? number.format(value)
                          : value}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
