import { cn } from "cn";
import { useId } from "react";
import { useTranslation } from "react-i18next";

interface BeadRodProps {
  /** Goals per game: how many beads (BR-123). */
  count: number;
  value: number | null;
  side: "a" | "b";
  /** The pair's names, for the beads' labels. */
  names: string;
  onChange: (value: number) => void;
  disabled?: boolean;
}

/**
 * The score counter of a foosball table (Figma: Bead rod): tapping bead n
 * sets the score to n. The beads are native radios, so arrow keys move
 * along the rod; each is a 44 px target, in two rows of five on a phone and
 * one row from a 28 rem panel up.
 */
export function BeadRod({
  count,
  value,
  side,
  names,
  onChange,
  disabled = false,
}: BeadRodProps) {
  const { t } = useTranslation();
  const name = useId();

  return (
    <fieldset className="@container">
      <legend className="sr-only">
        {t("results.beads.legend", { names })}
      </legend>
      <div className="grid grid-cols-5 @md:grid-cols-10">
        {Array.from({ length: count }, (_, i) => i + 1).map((n) => (
          <label
            key={n}
            className="relative flex h-11 cursor-pointer items-center justify-center before:absolute before:inset-x-0 before:top-1/2 before:h-0.5 before:-translate-y-1/2 before:bg-bead-rod"
          >
            <input
              type="radio"
              name={name}
              value={n}
              checked={value === n}
              disabled={disabled}
              aria-label={t("results.beads.bead", { count: n, names })}
              onChange={() => {
                onChange(n);
              }}
              className="peer sr-only"
            />
            <span
              aria-hidden="true"
              className={cn(
                "relative size-[22px] rounded-full border-2 peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-background",
                value !== null && n <= value
                  ? side === "a"
                    ? "border-team-a bg-team-a"
                    : "border-team-b bg-team-b"
                  : "border-bead-rod bg-bead-empty",
              )}
            />
          </label>
        ))}
      </div>
    </fieldset>
  );
}
