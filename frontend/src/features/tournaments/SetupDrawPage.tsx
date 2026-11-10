import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-033, BR-031–BR-033).
export function SetupDrawPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="4" title={t("tournaments.setupDraw.title")} />
  );
}
