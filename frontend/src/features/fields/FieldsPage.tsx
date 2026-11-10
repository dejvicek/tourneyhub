import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";

import { FieldsView } from "./FieldsView";
import { useFieldsScreen } from "./useFieldsScreen";

/**
 * Screen 6b: fields now playing and the waiting list (FR-090–FR-094).
 * Moving a match (6c), editing the fields (6d) and entering a result open
 * over it (<Outlet />).
 */
export function FieldsPage() {
  const { t } = useTranslation();
  const screen = useFieldsScreen();
  const { model } = screen;
  const title = t("fields.now.title");

  return (
    <section className="space-y-6">
      <DocumentTitle screen={title} />
      <h1 className="sr-only">{title}</h1>
      {model ? (
        <FieldsView
          leagueId={screen.leagueId}
          model={model}
          play={screen.play}
          resultHref={screen.resultHref}
          moveHref={screen.moveHref}
          manageHref={screen.manageHref}
        />
      ) : (
        <p role={screen.failed ? "alert" : "status"}>
          {screen.failed ? t("roundRobin.loadFailed") : t("loading")}
        </p>
      )}
      <Outlet />
    </section>
  );
}
