import { type CSSProperties, useId } from "react";
import { useTranslation } from "react-i18next";

import type { Progress } from "./model";

/** "7 of 15 matches played", the round and a thin bar (screen 6). */
export function ProgressLine({ progress }: { progress: Progress }) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap justify-between gap-x-4 text-body-sm">
        <span id={id}>
          {t("roundRobin.progress.played", {
            count: progress.total,
            played: progress.played,
          })}
        </span>
        {progress.currentRound !== null && (
          <span className="text-muted-foreground">
            {t("roundRobin.progress.round", {
              round: progress.currentRound,
              rounds: progress.rounds,
            })}
          </span>
        )}
      </div>
      <div
        role="progressbar"
        aria-labelledby={id}
        aria-valuemin={0}
        aria-valuemax={progress.total}
        aria-valuenow={progress.played}
        className="h-1.5 overflow-hidden rounded-full bg-nav-active"
      >
        <div
          className="h-full w-(--progress) rounded-full bg-primary"
          // A custom property is not in CSSProperties; the value is a length.
          style={
            {
              "--progress": `${String(progress.total === 0 ? 0 : (progress.played / progress.total) * 100)}%`,
            } as CSSProperties
          }
        />
      </div>
    </div>
  );
}
