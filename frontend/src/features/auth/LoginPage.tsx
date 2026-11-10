import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-003).
export function LoginPage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("auth.login.title")} />;
}
