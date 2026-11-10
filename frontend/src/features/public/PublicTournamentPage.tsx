import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-070–FR-072).
export function PublicTournamentPage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("publicView.tournament.title")} />;
}
