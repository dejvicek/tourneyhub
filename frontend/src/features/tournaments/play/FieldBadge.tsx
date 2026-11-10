import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

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
      className={cn(size === "large" && "px-3 py-1 text-body-md", className)}
    >
      {t("roundRobin.field", { number })}
    </Badge>
  );
}
