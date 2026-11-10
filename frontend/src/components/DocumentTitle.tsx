import { useTranslation } from "react-i18next";

/** The screen's <title>, one per screen (WCAG 2.4.2, docs/frontend-style.md §6). */
export function DocumentTitle({ screen }: { screen: string }) {
  const { t } = useTranslation();
  return <title>{t("app.title", { screen })}</title>;
}
