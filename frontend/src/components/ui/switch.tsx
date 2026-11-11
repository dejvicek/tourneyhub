import { Switch as SwitchPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

// The track is drawn 52 x 30, as in the design; the button itself is 44 px
// high, so that it is a 44 px target (WCAG 2.5.8, guide §6).

function Switch({
  className,
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "peer group relative inline-flex h-11 w-[52px] shrink-0 items-center rounded-full bg-transparent outline-hidden disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <span
        aria-hidden="true"
        data-slot="switch-track"
        className="absolute inset-x-0 top-1/2 h-[30px] -translate-y-1/2 rounded-full border-2 border-input bg-input-background transition-colors group-focus-visible:ring-[3px] group-focus-visible:ring-ring group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-background group-data-[state=checked]:border-primary group-data-[state=checked]:bg-primary"
      />
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none relative block size-[22px] translate-x-1 rounded-full bg-input transition-transform data-[state=checked]:translate-x-[26px] data-[state=checked]:bg-primary-foreground motion-reduce:transition-none"
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
