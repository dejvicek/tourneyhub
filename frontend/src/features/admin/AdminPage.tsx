import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { PageFallback } from "@/components/PageFallback";
import { authQueries } from "@/features/auth/api";
import { paths } from "@/lib/paths";

import { OrganizersSection } from "./OrganizersSection";
import { SignupCodeSection } from "./SignupCodeSection";

/**
 * The admin area (FR-005, FR-006, ADR-007): the sign-up code and the
 * accounts. The server checks the admin flag on every call; this screen only
 * spares a non-admin the requests that would answer 403.
 */
export function AdminPage() {
  const { t } = useTranslation();
  const me = useQuery(authQueries.me());

  if (me.isPending) {
    return <PageFallback />;
  }
  if (me.data?.is_admin !== true) {
    return (
      <section className="mx-auto w-full max-w-md space-y-3">
        <DocumentTitle screen={t("admin.forbidden.title")} />
        <h1 className="font-display text-display-title">
          {t("admin.forbidden.title")}
        </h1>
        <p className="text-body-lg text-muted-foreground">
          {t("admin.forbidden.body")}
        </p>
        <Link
          to={paths.myLeagues}
          className="inline-flex min-h-11 items-center text-body-md font-bold text-primary underline underline-offset-4"
        >
          {t("auth.account.myLeagues")}
        </Link>
      </section>
    );
  }
  return (
    <section className="space-y-6">
      <DocumentTitle screen={t("admin.title")} />
      <header className="space-y-2">
        <h1 className="font-display text-display-title">{t("admin.title")}</h1>
        <p className="text-body-md text-muted-foreground">{t("admin.lead")}</p>
      </header>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <SignupCodeSection />
        <OrganizersSection myId={me.data.id} />
      </div>
    </section>
  );
}
