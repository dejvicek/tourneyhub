import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-032).
export function SetupPlayersPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="3" title={t("tournaments.setupPlayers.title")} />
  );
}
