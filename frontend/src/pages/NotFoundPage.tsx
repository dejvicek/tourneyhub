import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";
import { paths } from "@/lib/paths";

export function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <section className="space-y-4">
      <DocumentTitle screen={t("notFound.title")} />
      <h1 className="font-display text-display-screen">
        {t("notFound.title")}
      </h1>
      <p className="text-body-md text-muted-foreground">{t("notFound.body")}</p>
      <Button asChild variant="outline">
        <Link to={paths.home}>{t("notFound.home")}</Link>
      </Button>
    </section>
  );
}
