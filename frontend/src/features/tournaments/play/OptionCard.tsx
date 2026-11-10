import type { ReactNode } from "react";
import { useId } from "react";

import { RadioGroupItem } from "@/components/ui/radio-group";
import { cn } from "@/lib/utils";

interface OptionCardProps {
  value: string;
  title: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
}

/**
 * The design's Option card: a radio with a title and a description, the
 * whole card its label. Place inside a RadioGroup.
 */
export function OptionCard({
  value,
  title,
  description,
  disabled = false,
}: OptionCardProps) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      className={cn(
        "flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border-2 border-border-surface bg-card p-4 text-card-foreground has-data-[state=checked]:border-primary has-data-[state=checked]:bg-notice-info",
        disabled && "cursor-not-allowed opacity-70",
      )}
    >
      <RadioGroupItem
        id={id}
        value={value}
        disabled={disabled}
        aria-labelledby={`${id}-t`}
        aria-describedby={description === undefined ? undefined : `${id}-d`}
        className="mt-0.5"
      />
      <span className="space-y-1">
        <span id={`${id}-t`} className="block text-body-md font-bold">
          {title}
        </span>
        {description !== undefined && (
          <span
            id={`${id}-d`}
            className="block text-body-sm text-muted-foreground"
          >
            {description}
          </span>
        )}
      </span>
    </label>
  );
}
