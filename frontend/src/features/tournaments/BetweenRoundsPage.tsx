import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-040, FR-042).
export function BetweenRoundsPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="11" title={t("tournaments.betweenRounds.title")} />
  );
}
