import { useTranslation } from "react-i18next";

import { PlaceholderPage } from "@/components/PlaceholderPage";

// Placeholder (FR-012).
export function PlayersPage() {
  const { t } = useTranslation();
  return <PlaceholderPage title={t("players.list.title")} />;
}
