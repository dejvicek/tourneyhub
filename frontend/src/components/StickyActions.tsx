import type { ReactNode } from "react";

/**
 * The result sheet's actions: save, the walkover link, clear. They stay at
 * the bottom of the sheet while the form above scrolls, so that none sits
 * below the fold on a phone (390 × 844).
 */
export function StickyActions({ children }: { children: ReactNode }) {
  return (
    <div className="sticky bottom-0 z-10 -mx-6 -mb-6 flex flex-col gap-1 border-t border-border bg-popover px-6 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
      {children}
    </div>
  );
}
