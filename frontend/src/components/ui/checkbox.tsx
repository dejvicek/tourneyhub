import { Checkbox as CheckboxPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

import { CheckIcon } from "./icons";

// The box is drawn 36 px; the button itself is 44 x 44 px, so that it is a
// 44 px target (WCAG 2.5.8, FR-082, guide §6).

function Checkbox({
  className,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer group relative grid size-11 shrink-0 place-content-center rounded-[5px] outline-hidden disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <span
        aria-hidden="true"
        data-slot="checkbox-box"
        className="absolute inset-1 rounded-[5px] border-2 border-input bg-input-background transition-shadow group-focus-visible:ring-[3px] group-focus-visible:ring-ring group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-background group-aria-invalid:border-destructive group-data-[state=checked]:border-primary group-data-[state=checked]:bg-primary"
      />
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="relative grid place-content-center text-primary-foreground"
      >
        <CheckIcon className="size-5" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
