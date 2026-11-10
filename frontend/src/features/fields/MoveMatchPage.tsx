import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-093).
export function MoveMatchPage() {
  const { t } = useTranslation();
  return <PlaceholderPage screen="6c" title={t("fields.move.title")} />;
}
