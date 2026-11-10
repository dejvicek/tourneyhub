import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (§7.5). The result overlay opens over it (<Outlet />).
export function KnockoutPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="9" title={t("tournaments.knockout.title")}>
      <Outlet />
    </PlaceholderPage>
  );
}
