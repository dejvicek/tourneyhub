import { useTranslation } from "react-i18next";

import { DocumentTitle } from "@/components/DocumentTitle";
import { TempChrome } from "@/features/tournaments/play/TempChrome";

import { FieldsView } from "./FieldsView";
import { useFieldsScreen } from "./useFieldsScreen";

/** Screen 6b: fields now playing and the waiting list (FR-090–FR-094). */
export function FieldsPage() {
  const { t } = useTranslation();
  const screen = useFieldsScreen();
  const { model } = screen;

  return (
    <TempChrome
      leagueId={screen.leagueId}
      tournamentId={screen.tournamentId}
      title={model?.tournament.name ?? t("fields.now.title")}
    >
      <DocumentTitle screen={t("fields.now.title")} />
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
    </TempChrome>
  );
}
