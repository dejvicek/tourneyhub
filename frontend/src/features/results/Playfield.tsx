import type { ReactNode } from "react";

/**
 * The green table the two side panels sit on (Figma: Playfield), with its
 * centre line and circle. Decoration only.
 */
export function Playfield({ children }: { children: ReactNode }) {
  return (
    <div className="relative isolate space-y-7 overflow-hidden rounded-xl bg-field p-3.5">
      <span
        aria-hidden="true"
        className="absolute inset-x-0 top-1/2 -z-10 h-0.5 bg-field-foreground/40"
      />
      <span
        aria-hidden="true"
        className="absolute top-1/2 left-1/2 -z-10 size-24 -translate-1/2 rounded-full border-2 border-field-foreground/40"
      />
      {children}
    </div>
  );
}
