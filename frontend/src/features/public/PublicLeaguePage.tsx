import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-070–FR-072).
export function PublicLeaguePage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("publicView.league.title")} />;
}
