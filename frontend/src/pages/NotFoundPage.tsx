import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
        {t("notFound.title")}
      </h1>
      <p className="text-muted-foreground">{t("notFound.body")}</p>
      <Button asChild variant="outline">
        <Link to="/">{t("notFound.home")}</Link>
      </Button>
    </section>
  );
}
