import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-090, BR-132).
export function EditFieldsPage() {
  const { t } = useTranslation();
  return <PlaceholderPage screen="6d" title={t("fields.edit.title")} />;
}
