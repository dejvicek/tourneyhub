import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (§7.5).
export function KnockoutPage() {
  const { t } = useTranslation();
  return <PlaceholderPage screen="9" title={t("tournaments.knockout.title")} />;
}
