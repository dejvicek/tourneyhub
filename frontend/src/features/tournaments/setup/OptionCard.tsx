import { cn } from "cn";
import { useId } from "react";

import { RadioGroupItem } from "@/components/ui/radio-group";

interface OptionCardProps {
  value: string;
  title: string;
  description: string;
}

/** One choice of the design's Option card: a radio inside a card that is the whole target. */
export function OptionCard({ value, title, description }: OptionCardProps) {
  const id = useId();
  const titleId = `${id}-title`;
  const descriptionId = `${id}-description`;

  return (
    <label
      htmlFor={id}
      className={cn(
        "flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border-2 border-border-surface bg-card p-4",
        "has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-notice-info",
        "has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
      )}
    >
      <RadioGroupItem
        id={id}
        value={value}
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="mt-0.5 focus-visible:ring-0 focus-visible:ring-offset-0"
      />
      <span className="grid gap-0.5">
        <span id={titleId} className="text-body-md font-bold">
          {title}
        </span>
        <span id={descriptionId} className="text-body-sm text-muted-foreground">
          {description}
        </span>
      </span>
    </label>
  );
}
