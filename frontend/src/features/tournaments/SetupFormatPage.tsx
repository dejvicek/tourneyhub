import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-030, FR-031).
export function SetupFormatPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="2" title={t("tournaments.setupFormat.title")} />
  );
}
