import { useTranslation } from "react-i18next";

import { BeadRod } from "./BeadRod";

interface SidePanelProps {
  side: "a" | "b";
  names: string;
  seed: number | null;
  goalsPerGame: number;
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
}

/**
 * One pair on the result screen (Figma: Side panel): name, seed, the big
 * score and the bead rod. The score is also typed, for a score beyond the
 * beads or 0 (BR-123).
 */
export function SidePanel({
  side,
  names,
  seed,
  goalsPerGame,
  value,
  onChange,
  disabled = false,
}: SidePanelProps) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2.5 rounded-lg border border-border-surface bg-card px-3 pt-4 pb-2 text-card-foreground">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-display text-display-name break-words">{names}</p>
          {seed !== null && (
            <p className="text-body-sm text-muted-foreground">
              {t("results.seed", { seed })}
            </p>
          )}
        </div>
        <input
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete="off"
          disabled={disabled}
          aria-label={t("results.goalsFor", { names })}
          placeholder={t("results.noScore")}
          value={value === null ? "" : String(value)}
          onChange={(event) => {
            const digits = event.target.value.replace(/\D/g, "").slice(0, 3);
            onChange(digits === "" ? null : Number(digits));
          }}
          // Size and colour stay out of cn, which takes text styles for colours.
          className={
            side === "a"
              ? "h-18 w-24 shrink-0 rounded-md border-b-2 border-input bg-transparent text-right font-display text-score-xl text-team-a outline-hidden placeholder:text-muted-foreground focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              : "h-18 w-24 shrink-0 rounded-md border-b-2 border-input bg-transparent text-right font-display text-score-xl text-team-b outline-hidden placeholder:text-muted-foreground focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          }
        />
      </div>
      <BeadRod
        count={goalsPerGame}
        value={value}
        side={side}
        names={names}
        disabled={disabled}
        onChange={onChange}
      />
    </div>
  );
}
