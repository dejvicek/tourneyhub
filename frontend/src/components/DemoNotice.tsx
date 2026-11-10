import { useTranslation } from "react-i18next";

import { isDemoMode } from "@/lib/demoMode";

/** Tells the viewer that the demo's data is made up; nothing outside demo mode. */
export function DemoNotice() {
  const { t } = useTranslation();

  if (!isDemoMode(import.meta.env)) {
    return null;
  }
  return (
    <p className="rounded-lg bg-notice-info px-4 py-2 text-caption text-notice-info-foreground">
      {t("demo.notice")}
    </p>
  );
}
