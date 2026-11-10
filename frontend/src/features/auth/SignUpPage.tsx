import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-001, FR-002).
export function SignUpPage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("auth.signUp.title")} />;
}
