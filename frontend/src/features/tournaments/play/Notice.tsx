import type { ReactNode } from "react";

import { InfoIcon, WarningIcon } from "./icons";

interface NoticeProps {
  variant: "info" | "warning";
  title?: string;
  children: ReactNode;
}

/** The design's Notice: an info or a warning with a title and a body. */
export function Notice({ variant, title, children }: NoticeProps) {
  const Icon = variant === "info" ? InfoIcon : WarningIcon;
  return (
    <div
      className={
        variant === "info"
          ? "flex gap-3 rounded-lg bg-notice-info px-4 py-3.5 text-notice-info-foreground"
          : "flex gap-3 rounded-lg bg-notice-warning px-4 py-3.5 text-notice-warning-foreground"
      }
    >
      <Icon className="mt-0.5 size-5 shrink-0" />
      <div className="space-y-1 text-body-sm">
        {title !== undefined && (
          <p className="text-body-md font-bold">{title}</p>
        )}
        <div>{children}</div>
      </div>
    </div>
  );
}
