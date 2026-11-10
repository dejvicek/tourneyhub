import { useTranslation } from "react-i18next";

import { PlaceholderSheet } from "@/components/PlaceholderSheet";

// Placeholder (FR-093), an overlay over the fields (6b).
export function MoveMatchPage() {
  const { t } = useTranslation();
  return <PlaceholderSheet screen="6c" title={t("fields.move.title")} />;
}
