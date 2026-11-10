import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-090–FR-092).
export function FieldsPage() {
  const { t } = useTranslation();
  return <PlaceholderPage screen="6b" title={t("fields.now.title")} />;
}
