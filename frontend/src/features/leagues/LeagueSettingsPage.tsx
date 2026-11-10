import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-011, FR-013, FR-070).
export function LeagueSettingsPage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("leagues.settings.title")} />;
}
