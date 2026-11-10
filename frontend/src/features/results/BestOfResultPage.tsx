import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-050, BR-120–BR-124).
export function BestOfResultPage() {
  const { t } = useTranslation();
  return <PlaceholderPage screen="7b" title={t("results.bestOf.title")} />;
}
