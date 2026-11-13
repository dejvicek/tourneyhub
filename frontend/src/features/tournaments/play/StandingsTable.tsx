import { Fragment } from "react";
import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { cn } from "@/lib/utils";

import { entryPlayers, type PlayModel, shortName } from "./model";

type PlayStandingRow = components["schemas"]["PlayStandingRow"];
type FormResult = PlayStandingRow["form"][number];

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
 * record, game difference in BO3 and BO5, score difference and points. A
 * shared place repeats its number.
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
  // BR-101: game difference ranks in every format, but in BO1 and BO2 it
  // follows from won and lost, so its column only costs width on a phone.
  const format = model.group?.match_format;
  const showGames = format === "bo3" || format === "bo5";
  const columns = showGames ? 5 : 4;

  return (
    <table className="w-full border-separate border-spacing-0 text-left">
      <caption className="sr-only">{caption}</caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">{t("roundRobin.standings.place")}</th>
          <th scope="col">{t("roundRobin.standings.entry")}</th>
          {showGames && (
            <th scope="col">{t("roundRobin.standings.gameDifference")}</th>
          )}
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
                  <td colSpan={columns} className="py-2">
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
                          played: t("roundRobin.standings.played", {
                            count: row.played,
                          }),
                          won: t("roundRobin.standings.won", {
                            count: row.won,
                          }),
                          drawn: t("roundRobin.standings.drawn", {
                            count: row.drawn,
                          }),
                          lost: t("roundRobin.standings.lost", {
                            count: row.lost,
                          }),
                          satOut: t("roundRobin.standings.satOut", {
                            count: row.sat_out,
                          }),
                        },
                      )}
                    </span>
                    {row.bh1 !== null && (
                      <span>
                        {t("roundRobin.standings.buchholz", {
                          bh1: row.bh1,
                          bh2: row.bh2 ?? 0,
                        })}
                      </span>
                    )}
                  </span>
                </td>
                {showGames && (
                  <td className="border-t py-3 pr-2 text-right text-body-sm">
                    {signed.format(row.game_difference)}
                    {/* The head is for screen readers; on screen the two
                        signed numbers need a word each (BR-101, FR-082). */}
                    <span
                      aria-hidden="true"
                      className="block text-caption text-muted-foreground"
                    >
                      {t("roundRobin.standings.gamesLabel")}
                    </span>
                  </td>
                )}
                <td className="border-t py-3 pr-2 text-right text-body-sm text-muted-foreground">
                  {signed.format(row.score_difference)}
                  {showGames && (
                    <span aria-hidden="true" className="block text-caption">
                      {t("roundRobin.standings.scoreLabel")}
                    </span>
                  )}
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
