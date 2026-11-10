import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface NoticeProps {
  tone: "info" | "warning";
  title: string;
  children?: ReactNode;
  className?: string;
}

/** The design's Notice: a tinted box with a bold title (info or warning). */
export function Notice({ tone, title, children, className }: NoticeProps) {
  return (
    <div
      className={cn(
        "rounded-lg px-4 py-3.5",
        tone === "info"
          ? "bg-notice-info text-notice-info-foreground"
          : "bg-notice-warning text-notice-warning-foreground",
        className,
      )}
    >
      <p className="text-body-md font-bold">{title}</p>
      {children !== undefined && (
        <div className="mt-1 text-body-sm">{children}</div>
      )}
    </div>
  );
}
