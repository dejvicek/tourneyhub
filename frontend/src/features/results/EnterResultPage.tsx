import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { ResponsiveSheet } from "@/components/ResponsiveSheet";

import { ResultEntry } from "./ResultEntry";
import { useMatchTitle, useResultScreen } from "./useResultScreen";

/**
 * Screens 7 and 7b, over the screen that opened them: enter, change or
 * clear a match's result, or record a walkover (FR-050–FR-053, FR-082,
 * BR-090–BR-095, BR-120–BR-124). A BO1 match gets the bead form (7), a
 * best-of match BestOfResultPage (7b).
 */
export function EnterResultPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const screen = useResultScreen();
  const matchTitle = useMatchTitle();
  const { model } = screen;
  const info = model?.matches.get(screen.matchId);

  return (
    <ResponsiveSheet
      title={model && info ? matchTitle(model, info) : t("results.enter.title")}
      description={
        model && info
          ? t(
              info.field === undefined
                ? `results.subtitle.${info.format}`
                : `results.subtitleOnField.${info.format}`,
              {
                tournament: model.tournament.name,
                field: info.field?.number ?? 0,
              },
            )
          : undefined
      }
    >
      {model ? (
        <ResultEntry
          leagueId={screen.leagueId}
          model={model}
          play={screen.play}
          matchId={screen.matchId}
          onDone={() => {
            void navigate("..");
          }}
        />
      ) : (
        <p role={screen.failed ? "alert" : "status"}>
          {screen.failed ? t("roundRobin.loadFailed") : t("loading")}
        </p>
      )}
    </ResponsiveSheet>
  );
}
