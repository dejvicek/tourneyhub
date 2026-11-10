import { cn } from "cn";
import type { ReactNode } from "react";

import { InfoIcon, WarningIcon } from "./icons";

interface NoticeProps {
  variant: "info" | "warning";
  title: string;
  children?: ReactNode;
  className?: string;
}

/**
 * The design's Notice. A warning is announced as the choices change
 * (`role="status"`, docs/frontend-style.md §6); an info notice is plain text.
 */
export function Notice({ variant, title, children, className }: NoticeProps) {
  const Symbol = variant === "warning" ? WarningIcon : InfoIcon;
  return (
    <div
      role={variant === "warning" ? "status" : undefined}
      className={cn(
        "flex gap-3 rounded-lg px-4 py-3.5",
        variant === "warning"
          ? "bg-notice-warning text-notice-warning-foreground"
          : "bg-notice-info text-notice-info-foreground",
        className,
      )}
    >
      <Symbol className="mt-0.5 size-5 shrink-0" />
      <div className="grid gap-1">
        <p className="text-body-md font-bold">{title}</p>
        {children !== undefined && (
          <div className="text-body-sm">{children}</div>
        )}
      </div>
    </div>
  );
}
