import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface StepperProps {
  label: string;
  hint?: string;
  error?: string;
  value: string;
  onChange: (value: string) => void;
  min?: number;
}

/**
 * A whole number with − and + (the design's inline Stepper, screen 2): 44 px
 * buttons for the thumb, and a field to type into.
 */
export function Stepper({
  label,
  hint,
  error,
  value,
  onChange,
  min = 1,
}: StepperProps) {
  const { t } = useTranslation();
  const id = useId();
  const number = Number.parseInt(value, 10);
  const current = Number.isNaN(number) ? min : number;
  const describedBy = [
    hint === undefined ? undefined : `${id}-hint`,
    error === undefined ? undefined : `${id}-error`,
  ]
    .filter((part) => part !== undefined)
    .join(" ");

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-body-sm">
        {label}
      </Label>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          aria-label={t("leagues.settings.league.decrease", { label })}
          size="icon"
          className="rounded-lg"
          disabled={current <= min}
          onClick={() => {
            onChange(String(Math.max(min, current - 1)));
          }}
        >
          <span aria-hidden="true" className="text-display-section">
            −
          </span>
        </Button>
        <Input
          id={id}
          inputMode="numeric"
          pattern="[0-9]*"
          value={value}
          aria-invalid={error === undefined ? undefined : true}
          aria-describedby={describedBy === "" ? undefined : describedBy}
          className="w-20 text-center text-base"
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
        <Button
          type="button"
          variant="outline"
          aria-label={t("leagues.settings.league.increase", { label })}
          size="icon"
          className="rounded-lg"
          onClick={() => {
            onChange(String(current + 1));
          }}
        >
          <span aria-hidden="true" className="text-display-section">
            +
          </span>
        </Button>
      </div>
      {hint !== undefined && (
        <p id={`${id}-hint`} className="text-body-sm text-muted-foreground">
          {hint}
        </p>
      )}
      {error !== undefined && (
        <p
          id={`${id}-error`}
          className="text-body-sm font-bold text-destructive"
        >
          {error}
        </p>
      )}
    </div>
  );
}
