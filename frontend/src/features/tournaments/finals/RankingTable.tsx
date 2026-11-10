import { useTranslation } from "react-i18next";

import type { ParticipantRead, RankingRead, RankingRow } from "@/demo/contract";
import { cn } from "@/lib/utils";

interface RankingTableProps {
  ranking: RankingRead;
  participants: readonly ParticipantRead[];
  entryName: (entryId: string) => string;
  /** The table's accessible name, as its heading says it. */
  caption: string;
}

function valueOf(row: RankingRow, key: RankingRead["tiebreakers"][number]) {
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
  ranking,
  participants,
  entryName,
  caption,
}: RankingTableProps) {
  const { t, i18n } = useTranslation();
  const number = new Intl.NumberFormat(i18n.resolvedLanguage, {
    signDisplay: "exceptZero",
  });
  const cut = ranking.qualifiers;
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
            {ranking.tiebreakers.map((key) => (
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
          {ranking.rows.map((row, index) => {
            const info = participants.find((p) => p.entry_id === row.entry_id);
            const label = row.is_disabled
              ? t("finals.rounds.disabledLabel")
              : info?.joined_round != null
                ? t("finals.rounds.joinedLabel", { round: info.joined_round })
                : null;
            return (
              <tr
                key={row.entry_id}
                className={cn(
                  "border-t border-border",
                  cut !== null &&
                    index === cut - 1 &&
                    "border-b-2 border-b-primary",
                )}
              >
                <td className="py-2.5 pr-2 font-display text-score-s">
                  {row.place}
                </td>
                <td className="py-2.5">
                  <span
                    className={cn(row.is_disabled && "text-muted-foreground")}
                  >
                    {entryName(row.entry_id)}
                  </span>
                  {label !== null && (
                    <span className="block text-caption text-muted-foreground">
                      {label}
                    </span>
                  )}
                </td>
                <td className="py-2.5 text-end font-bold">{row.points}</td>
                {ranking.tiebreakers.map((key) => (
                  <td key={key} className="py-2.5 text-end">
                    {key === "score_difference"
                      ? number.format(valueOf(row, key))
                      : valueOf(row, key)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
