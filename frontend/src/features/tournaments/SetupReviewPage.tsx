import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-034–FR-036).
export function SetupReviewPage() {
  const { t } = useTranslation();
  return (
    <PlaceholderPage screen="5" title={t("tournaments.setupReview.title")} />
  );
}
