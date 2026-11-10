import { useId } from "react";

import { Button } from "@/components/ui/button";

import { MinusIcon, PlusIcon } from "./icons";

interface StepperProps {
  label: string;
  hint: string;
  decreaseLabel: string;
  increaseLabel: string;
  value: number;
  min: number;
  max: number;
  onValueChange: (value: number) => void;
}

/** A "− value +" row (Figma: Stepper, drawn inline on screen 2). */
export function Stepper({
  label,
  hint,
  decreaseLabel,
  increaseLabel,
  value,
  min,
  max,
  onValueChange,
}: StepperProps) {
  const labelId = useId();
  const hintId = useId();

  return (
    <div
      role="group"
      aria-labelledby={labelId}
      aria-describedby={hintId}
      className="flex items-center justify-between gap-4"
    >
      <div className="grid gap-1">
        <span id={labelId} className="text-body-sm font-bold">
          {label}
        </span>
        <p id={hintId} className="text-body-sm text-muted-foreground">
          {hint}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {/* TODO(foundation-buttons): size-11 until Button has a 44 px icon size */}
        <Button
          type="button"
          variant="outline"
          className="size-11 rounded-full"
          aria-label={decreaseLabel}
          disabled={value <= min}
          onClick={() => {
            onValueChange(value - 1);
          }}
        >
          <MinusIcon />
        </Button>
        <output
          aria-live="polite"
          className="min-w-10 text-center font-display text-score-m"
        >
          {value}
        </output>
        <Button
          type="button"
          variant="outline"
          className="size-11 rounded-full"
          aria-label={increaseLabel}
          disabled={value >= max}
          onClick={() => {
            onValueChange(value + 1);
          }}
        >
          <PlusIcon />
        </Button>
      </div>
    </div>
  );
}
