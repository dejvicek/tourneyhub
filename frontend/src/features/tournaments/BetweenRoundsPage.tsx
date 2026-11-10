import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-040, FR-042). The result overlay opens over it (<Outlet />).
export function BetweenRoundsPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="11" title={t("tournaments.betweenRounds.title")}>
      <Outlet />
    </PlaceholderPage>
  );
}
