import { cn } from "cn";
import { Fragment } from "react";
import { useTranslation } from "react-i18next";

import type { FormResult, PlayStandingRow } from "@/demo/contract";

import { entryPlayers, type PlayModel, shortName } from "./model";

interface StandingsTableProps {
  model: PlayModel;
  rows: readonly PlayStandingRow[];
  /** Draws the "Top N go through" line after row N (screen 8). */
  cutAfter?: number;
  caption: string;
}

/** Shape, not colour, tells the results apart (Figma: Form dot). */
function FormDots({ form }: { form: readonly FormResult[] }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1">
      {form.map((result, i) => (
        <span
          // The results are in a fixed order; the index is their identity.
          key={i}
          aria-hidden="true"
          className={cn(
            "flex size-2.5 overflow-hidden rounded-full border-2 border-foreground",
            result === "won" && "bg-foreground",
          )}
        >
          {result === "drawn" && <span className="w-1/2 bg-foreground" />}
        </span>
      ))}
      <span className="sr-only">
        {t("roundRobin.standings.form", {
          results: form
            .map((result) => t(`roundRobin.standings.formResult.${result}`))
            .join(", "),
        })}
      </span>
    </span>
  );
}

/**
 * Live group-phase standings (FR-060, BR-101): place, the pair, form, the
 * record, score difference and points. A shared place repeats its number.
 */
export function StandingsTable({
  model,
  rows,
  cutAfter,
  caption,
}: StandingsTableProps) {
  const { t, i18n } = useTranslation();
  const signed = new Intl.NumberFormat(i18n.resolvedLanguage, {
    signDisplay: "exceptZero",
  });
  const showSatOut = rows.some((row) => row.sat_out > 0);

  return (
    <table className="w-full border-separate border-spacing-0 text-left">
      <caption className="sr-only">{caption}</caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">{t("roundRobin.standings.place")}</th>
          <th scope="col">{t("roundRobin.standings.entry")}</th>
          <th scope="col">{t("roundRobin.standings.difference")}</th>
          <th scope="col">{t("roundRobin.standings.points")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => {
          const names = entryPlayers(model, row.entry_id).map(shortName);
          return (
            <Fragment key={row.entry_id}>
              {cutAfter === index && (
                <tr>
                  <td colSpan={4} className="py-2">
                    <span className="flex items-center gap-2 text-caption font-bold text-secondary-foreground">
                      <span className="h-0 flex-1 border-t-2 border-dashed border-primary" />
                      {t("roundRobin.standings.cut", { count: cutAfter })}
                      <span className="h-0 flex-1 border-t-2 border-dashed border-primary" />
                    </span>
                  </td>
                </tr>
              )}
              <tr className="align-top">
                <th
                  scope="row"
                  className={cn(
                    "w-9 border-t py-3 pr-2 font-display text-score-m",
                    row.place === 1 && "text-secondary-foreground",
                  )}
                >
                  {t("roundRobin.standings.placeValue", { place: row.place })}
                </th>
                <td className="border-t py-3 pr-2">
                  {names.map((name, i) => (
                    <span
                      key={name}
                      className={cn(
                        "block text-body-md",
                        i === 0 && "font-bold",
                      )}
                    >
                      {name}
                    </span>
                  ))}
                  <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-muted-foreground">
                    <FormDots form={row.form} />
                    <span>
                      {t(
                        showSatOut
                          ? "roundRobin.standings.recordWithSatOut"
                          : "roundRobin.standings.record",
                        {
                          played: row.played,
                          won: row.won,
                          drawn: row.drawn,
                          lost: row.lost,
                          satOut: row.sat_out,
                        },
                      )}
                    </span>
                  </span>
                </td>
                <td className="border-t py-3 pr-2 text-right text-body-sm text-muted-foreground">
                  {signed.format(row.score_difference)}
                </td>
                <td className="w-10 border-t py-3 text-right font-display text-score-l">
                  {row.points}
                </td>
              </tr>
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
