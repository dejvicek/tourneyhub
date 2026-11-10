import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-061, FR-022).
export function SeasonStandingsPage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("standings.season.title")} />;
}
