import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-045, BR-081–BR-084).
export function StartKnockoutPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="13" title={t("tournaments.startKnockout.title")} />
  );
}
