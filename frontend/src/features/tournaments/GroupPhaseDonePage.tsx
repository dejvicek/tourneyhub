import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-040, FR-045).
export function GroupPhaseDonePage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="8" title={t("tournaments.groupPhaseDone.title")} />
  );
}
