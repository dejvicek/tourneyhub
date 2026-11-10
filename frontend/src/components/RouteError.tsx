import { useTranslation } from "react-i18next";
import { isRouteErrorResponse, useRouteError } from "react-router";

import { ApiError } from "@/api/client";
import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";

/**
 * The ErrorBoundary of the root route and of each area (docs/frontend-style.md
 * §9): an unexpected failure, such as a lazy chunk that did not load or a
 * screen's main resource that threw. A missing route or record says so.
 */
export function RouteError() {
  const { t } = useTranslation();
  const error = useRouteError();
  const missing =
    (isRouteErrorResponse(error) && error.status === 404) ||
    (error instanceof ApiError && error.status === 404);

  return (
    <section role="alert" className="space-y-4 p-6">
      <DocumentTitle screen={t("routeError.title")} />
      <h1 className="font-display text-display-screen">
        {t("routeError.title")}
      </h1>
      <p className="text-body-md text-muted-foreground">
        {missing ? t("routeError.notFound") : t("routeError.body")}
      </p>
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          window.location.reload();
        }}
      >
        {t("routeError.reload")}
      </Button>
    </section>
  );
}
