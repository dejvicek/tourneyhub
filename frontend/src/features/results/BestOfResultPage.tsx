import { useTranslation } from "react-i18next";

import { PlaceholderSheet } from "@/components/PlaceholderSheet";

// Placeholder (FR-050, BR-120–BR-124). Not a route: EnterResultPage shows it
// for a match of more than one game.
export function BestOfResultPage() {
  const { t } = useTranslation();
  return <PlaceholderSheet screen="7b" title={t("results.bestOf.title")} />;
}
