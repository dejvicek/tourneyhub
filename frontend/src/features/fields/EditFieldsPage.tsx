import { useTranslation } from "react-i18next";

import { PlaceholderSheet } from "@/components/PlaceholderSheet";

// Placeholder (FR-090, BR-132), an overlay over the fields (6b).
export function EditFieldsPage() {
  const { t } = useTranslation();
  return <PlaceholderSheet screen="6d" title={t("fields.edit.title")} />;
}
