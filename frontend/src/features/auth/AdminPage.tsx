import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-005, FR-006, ADR-007).
export function AdminPage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("auth.admin.title")} />;
}
