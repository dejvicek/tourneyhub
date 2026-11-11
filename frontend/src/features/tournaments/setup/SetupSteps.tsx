import { useTranslation } from "react-i18next";

import { CheckIcon } from "@/components/ui/icons";
import { cn } from "@/lib/utils";

import type { TournamentType } from "./format";

export type SetupStep = 1 | 2 | 3 | 4;

const STEP_LABELS = [
  "tournaments.setup.steps.format",
  "tournaments.setup.steps.players",
  "tournaments.setup.steps.pairs",
  "tournaments.setup.steps.start",
] as const;

/** The third step is "Pairs" for DYP and Doubles, "Seeding" for Singles (Figma: Setup steps). */
function thirdStep(type: TournamentType | undefined) {
  switch (type) {
    case "singles":
      return "tournaments.setup.steps.seeding" as const;
    case "monster_dyp":
      return "tournaments.setup.steps.topPlayers" as const;
    case "doubles":
    case "dyp":
    case undefined:
      return STEP_LABELS[2];
  }
}

interface SetupStepsProps {
  current: SetupStep;
  type: TournamentType | undefined;
}

/** Progress through the four setup steps; an indicator, not navigation. */
export function SetupSteps({ current, type }: SetupStepsProps) {
  const { t } = useTranslation();
  const labels = [
    STEP_LABELS[0],
    STEP_LABELS[1],
    thirdStep(type),
    STEP_LABELS[3],
  ] as const;

  return (
    <nav aria-label={t("tournaments.setup.steps.label")}>
      <ol className="flex">
        {labels.map((label, index) => {
          const step = index + 1;
          const done = step < current;
          const active = step === current;
          return (
            <li
              key={label}
              aria-current={active ? "step" : undefined}
              className={cn(
                "relative flex flex-1 flex-col items-center gap-1.5 text-caption",
                step < labels.length &&
                  "after:absolute after:top-3.5 after:left-1/2 after:h-0.5 after:w-full after:-translate-y-1/2 after:bg-border",
                done && "after:bg-primary",
              )}
            >
              <span
                className={`relative z-10 grid size-7 place-content-center rounded-full border-2 font-display text-score-s ${
                  done || active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-background text-muted-foreground"
                }`}
              >
                {done ? <CheckIcon className="size-4" /> : step}
                <span className="sr-only">
                  {done ? t("tournaments.setup.steps.done") : ""}
                </span>
              </span>
              <span
                className={cn(
                  active ? "font-bold" : "text-muted-foreground",
                  "text-center",
                )}
              >
                {t(label)}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
