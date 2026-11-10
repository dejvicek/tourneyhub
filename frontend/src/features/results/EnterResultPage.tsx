import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { FieldBadge } from "@/features/tournaments/play/FieldBadge";
import { TempOverlay } from "@/features/tournaments/play/TempOverlay";

import { ResultEntry } from "./ResultEntry";
import { useMatchTitle, useResultScreen } from "./useResultScreen";

/**
 * Screens 7 and 7b: enter, change or clear a match's result, or record a
 * walkover (FR-050–FR-053, FR-082, BR-090–BR-095, BR-120–BR-124).
 */
export function EnterResultPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const screen = useResultScreen();
  const matchTitle = useMatchTitle();
  const { model } = screen;
  const info = model?.matches.get(screen.matchId);
  const title =
    model && info ? matchTitle(model, info) : t("results.enter.title");

  return (
    <>
      <DocumentTitle screen={t("results.documentTitle", { match: title })} />
      <TempOverlay
        title={
          <span className="flex flex-wrap items-center gap-3">
            {title}{" "}
            {info?.field !== undefined && (
              <FieldBadge number={info.field.number} />
            )}
          </span>
        }
        description={
          model && info
            ? t(`results.subtitle.${info.format}`, {
                tournament: model.tournament.name,
              })
            : undefined
        }
        closeTo={screen.backTo}
      >
        {model ? (
          <ResultEntry
            leagueId={screen.leagueId}
            model={model}
            play={screen.play}
            matchId={screen.matchId}
            onDone={() => {
              void navigate(screen.backTo);
            }}
          />
        ) : (
          <p role={screen.failed ? "alert" : "status"}>
            {screen.failed ? t("roundRobin.loadFailed") : t("loading")}
          </p>
        )}
      </TempOverlay>
    </>
  );
}
