import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-037, §7.13, §7.14).
export function FinishedPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="10" title={t("tournaments.finished.title")} />
  );
}
