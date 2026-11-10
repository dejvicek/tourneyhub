import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-004, ADR-006: the new password after an admin reset).
export function ChangePasswordPage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("auth.changePassword.title")} />;
}
