import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-044, FR-047, FR-048).
export function LateAndDisabledPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage
      screen="12"
      title={t("tournaments.lateAndDisabled.title")}
    />
  );
}
