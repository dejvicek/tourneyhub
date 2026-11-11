import { RadioGroup as RadioGroupPrimitive } from "radix-ui";
import { useId } from "react";

import { cn } from "@/lib/utils";

interface SegmentedControlProps<Value extends string> {
  label: string;
  hint?: string;
  value: Value;
  options: readonly { value: Value; label: string }[];
  onValueChange: (value: Value) => void;
  /** The checked option was clicked, or Space or Enter pressed on it. */
  onReselect?: (value: Value) => void;
  className?: string;
}

/**
 * The design's Segment: a tinted track with one selected pill. It is a radio
 * group (one choice, arrow keys), not tabs, because it switches no panel.
 */
export function SegmentedControl<Value extends string>({
  label,
  hint,
  value,
  options,
  onValueChange,
  onReselect,
  className,
}: SegmentedControlProps<Value>) {
  const labelId = useId();
  const hintId = useId();
  const known = (next: string): next is Value =>
    options.some((option) => option.value === next);

  return (
    <div className={cn("grid gap-2", className)}>
      <span id={labelId} className="text-body-sm font-bold">
        {label}
      </span>
      <RadioGroupPrimitive.Root
        value={value}
        onValueChange={(next) => {
          if (known(next)) {
            onValueChange(next);
          }
        }}
        aria-labelledby={labelId}
        aria-describedby={hint === undefined ? undefined : hintId}
        className="flex w-full items-center gap-1 rounded-lg bg-nav-active p-1"
      >
        {options.map((option) => (
          <RadioGroupPrimitive.Item
            key={option.value}
            value={option.value}
            onClick={() => {
              if (option.value === value) {
                onReselect?.(option.value);
              }
            }}
            onKeyDown={(event) => {
              // Radix keeps Enter from checking; it still means "this one".
              if (event.key === "Enter" && option.value === value) {
                onReselect?.(option.value);
              }
            }}
            className="inline-flex min-h-11 min-w-0 flex-1 items-center justify-center rounded-md px-2 py-1 text-center text-body-sm text-nav-active-foreground outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background data-[state=checked]:bg-card data-[state=checked]:font-bold data-[state=checked]:text-card-foreground"
          >
            {option.label}
          </RadioGroupPrimitive.Item>
        ))}
      </RadioGroupPrimitive.Root>
      {hint !== undefined && (
        <p id={hintId} className="text-body-sm text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}
