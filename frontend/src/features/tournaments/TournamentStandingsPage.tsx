import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-060), the Standings tab of every format.
export function TournamentStandingsPage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("tournaments.standings.title")} />;
}
