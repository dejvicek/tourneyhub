import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { TempOverlay } from "@/features/tournaments/play/TempOverlay";
import { useNames } from "@/features/tournaments/play/useNames";
import { useRouteParam } from "@/hooks/useRouteParam";

import { MoveMatchForm } from "./MoveMatchForm";
import { useFieldsScreen } from "./useFieldsScreen";

/** Screen 6c: move, swap, take off or place a match (FR-093). */
export function MoveMatchPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const matchId = useRouteParam("matchId");
  const screen = useFieldsScreen();
  const { model } = screen;
  const names = useNames(model);
  const info = model?.matches.get(matchId);
  const onField = info?.field !== undefined;
  const title = onField ? t("fields.move.title") : t("fields.move.putTitle");

  return (
    <>
      <DocumentTitle screen={title} />
      <TempOverlay
        title={title}
        description={
          info
            ? onField
              ? t("fields.move.nowOn", {
                  match: names.match(info.match.sides),
                  number: info.field?.number ?? 0,
                })
              : t("fields.move.nowWaiting", {
                  match: names.match(info.match.sides),
                  position: info.queue ?? 0,
                })
            : undefined
        }
        closeTo={screen.fieldsPath}
      >
        {model && (
          <MoveMatchForm
            leagueId={screen.leagueId}
            model={model}
            matchId={matchId}
            onDone={() => {
              void navigate(screen.fieldsPath);
            }}
          />
        )}
      </TempOverlay>
    </>
  );
}
