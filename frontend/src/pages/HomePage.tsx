import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { paths } from "@/lib/paths";

export function HomePage() {
  const { t } = useTranslation();

  return (
    <section className="space-y-4">
      <DocumentTitle screen={t("home.title")} />
      <h1 className="font-display text-display-title">{t("home.title")}</h1>
      <p className="text-body-lg text-muted-foreground">{t("home.lead")}</p>
      <Link
        to={paths.myLeagues}
        className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-button-sm text-primary-foreground"
      >
        {t("home.myLeagues")}
      </Link>
    </section>
  );
}
