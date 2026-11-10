import type { TFunction } from "i18next";

import type {
  GroupPhaseChoice,
  MatchFormat,
  TournamentFormatWrite,
  TournamentType,
} from "@/demo/contract";
import { rules } from "@/demo/rules";

import { longDate } from "./dates";

const TYPE_LABELS = {
  singles: "tournaments.setup.type.singles.title",
  doubles: "tournaments.setup.type.doubles.title",
  dyp: "tournaments.setup.type.dyp.title",
  monster_dyp: "tournaments.setup.type.monster_dyp.title",
} as const satisfies Record<TournamentType, string>;

export function typeLabel(t: TFunction, type: TournamentType): string {
  return t(TYPE_LABELS[type]);
}

export function formatLabel(t: TFunction, format: MatchFormat): string {
  return t(`tournaments.setup.matchFormat.${format}`);
}

/** "Round robin, once" and the like (Figma: Review > Group phase). */
export function groupPhaseLabel(
  t: TFunction,
  format: Pick<TournamentFormatWrite, "group_phase" | "round_robin_legs">,
): string {
  switch (format.group_phase satisfies GroupPhaseChoice) {
    case "round_robin":
      return format.round_robin_legs === 2
        ? t("tournaments.setup.groupPhase.roundRobinTwice")
        : t("tournaments.setup.groupPhase.roundRobinOnce");
    case "swiss":
      return t("tournaments.setup.groupPhase.swiss");
    case "monster_dyp":
      return t("tournaments.setup.groupPhase.monsterDyp");
    case "none":
      return t("tournaments.setup.groupPhase.none");
  }
}

/** The "points for sitting out" value; the value when on comes from rules.ts. */
export function sitOutLabel(t: TFunction, on: boolean): string {
  return on
    ? t("tournaments.setup.sitOut.on", { count: rules.sitOutPointsWhenOn })
    : t("tournaments.setup.sitOut.off");
}

export function dateLabel(isoDate: string): string {
  return longDate(isoDate);
}

/** The league's names for a pair or a player ("Honza K. & Eva H."). */
export function entryName(t: TFunction, names: readonly string[]): string {
  const [first, second] = names;
  return second === undefined
    ? (first ?? "")
    : t("tournaments.setup.pairName", { first, second });
}
