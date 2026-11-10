import { cn } from "cn";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import type { MatchSideRead } from "@/demo/contract";

import { FieldBadge } from "./FieldBadge";
import {
  type MatchInfo,
  type PlayModel,
  scoreOf,
  shortName,
  sideNames,
  sidesOf,
  winnerOf,
} from "./model";
import { useNames } from "./useNames";

interface ScheduleMatchProps {
  model: PlayModel;
  info: MatchInfo;
  /** Where the match's result is entered (screen 7). */
  resultHref: string;
}

function Side({
  model,
  side,
  won,
  align,
}: {
  model: PlayModel;
  side: MatchSideRead;
  won: boolean;
  align: "start" | "end";
}) {
  return (
    <span
      className={cn(
        "min-w-0 text-body-sm break-words",
        align === "end" && "text-right",
        won && "font-bold",
      )}
    >
      {sideNames(model, side).map((name) => (
        <span key={name} className="block">
          {shortName(name)}
        </span>
      ))}
    </span>
  );
}

/**
 * A group-phase match in the schedule (Figma: Schedule match): played with
 * its score, on a field with "Enter result", or waiting with its place in
 * line. Every match opens result entry, a waiting one too (FR-094).
 */
export function ScheduleMatch({ model, info, resultHref }: ScheduleMatchProps) {
  const { t } = useTranslation();
  const names = useNames(model);
  const { match, field, queue } = info;
  const winner = winnerOf(match);
  const score = scoreOf(info);
  const [a, b] = sidesOf(match);
  const sides = (center: ReactNode) => (
    <>
      <Side model={model} side={a} won={winner === "side_1"} align="start" />
      {center}
      <Side model={model} side={b} won={winner === "side_2"} align="end" />
    </>
  );
  const grid =
    "grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 rounded-lg p-3";

  if (match.outcome === null && field !== undefined) {
    return (
      <div
        className={cn(
          grid,
          "border-2 border-team-a bg-card text-card-foreground",
        )}
      >
        {sides(
          <span className="flex flex-col items-center gap-1.5">
            <FieldBadge number={field.number} />
            <Button asChild className="h-11 px-3 text-button-sm">
              {/* TODO(foundation-buttons): Compact 44 px is the default size after the rebase. */}
              <Link to={resultHref}>
                {t("roundRobin.schedule.enterResult")}
                <span className="sr-only">
                  {t("roundRobin.schedule.matchSuffix", {
                    match: names.match(match.sides),
                  })}
                </span>
              </Link>
            </Button>
          </span>,
        )}
      </div>
    );
  }

  const played = match.outcome !== null;
  return (
    <Link
      to={resultHref}
      className={cn(
        grid,
        "min-h-11 outline-hidden hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        played
          ? "border border-border-surface bg-card text-card-foreground"
          : "border-2 border-dashed border-input",
      )}
    >
      {sides(
        <span className="flex flex-col items-center text-center">
          {played ? (
            score === null ? (
              <span className="text-caption font-bold">
                {match.is_walkover
                  ? t("roundRobin.schedule.walkover")
                  : t("roundRobin.schedule.noScore")}
              </span>
            ) : (
              <span className="font-display text-score-m whitespace-nowrap">
                {t("roundRobin.score", { a: score[0], b: score[1] })}
              </span>
            )
          ) : (
            <>
              <span className="text-caption font-bold">
                {t("roundRobin.schedule.waiting")}
              </span>
              {queue !== undefined && (
                <span className="text-caption text-muted-foreground">
                  {t("roundRobin.schedule.inLine", { position: queue })}
                </span>
              )}
            </>
          )}
        </span>,
      )}
      <span className="sr-only">
        {played
          ? t("roundRobin.schedule.changeResult")
          : t("roundRobin.schedule.enterResult")}
      </span>
    </Link>
  );
}
