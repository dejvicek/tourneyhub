import type { ReactNode } from "react";

/** The design's Summary row: a muted label on the left, a bold value on the right. */
export function SummaryRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex justify-between gap-4 border-t border-border py-3 first:border-t-0">
      <dt className="text-body-md text-muted-foreground">{label}</dt>
      <dd className="text-right text-body-md font-bold">{children}</dd>
    </div>
  );
}
