import { cn } from "cn";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";

interface FieldBadgeProps {
  number: number;
  /** A free field is grey (Figma: Field badge, free variant). */
  free?: boolean;
  size?: "default" | "large";
  className?: string;
}

/** "Field 1": which field a match is on (FR-091). */
export function FieldBadge({
  number,
  free = false,
  size = "default",
  className,
}: FieldBadgeProps) {
  const { t } = useTranslation();
  return (
    <Badge
      variant={free ? "secondary" : "default"}
      className={cn(size === "large" && "px-3 py-1", className)}
    >
      {/* The size stays out of cn, which takes text styles for colours. */}
      <span className={size === "large" ? "text-body-md" : undefined}>
        {t("roundRobin.field", { number })}
      </span>
    </Badge>
  );
}
