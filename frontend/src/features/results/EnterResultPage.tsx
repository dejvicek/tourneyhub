import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-050–FR-053, FR-082).
export function EnterResultPage() {
  const { t } = useTranslation();
  return <PlaceholderPage screen="7" title={t("results.enter.title")} />;
}
