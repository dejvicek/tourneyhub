import { useTranslation } from "react-i18next";

import { DocumentTitle } from "@/components/DocumentTitle";
import { useRouteParam } from "@/hooks/useRouteParam";

import { StandingsNotes } from "./play/StandingsNotes";
import { StandingsTable } from "./play/StandingsTable";
import { usePlay } from "./play/usePlay";

/**
 * The Standings tab of every format (FR-060): live group-phase standings,
 * computed on read. A round robin shows points and the tie-break notes
 * (BR-101); Swiss and Monster DYP add BH1 and BH2 (BR-073).
 */
export function TournamentStandingsPage() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const { model, play, failed } = usePlay(leagueId, tournamentId);
  const title = t("tournaments.standings.title");

  return (
    <section className="space-y-4">
      <DocumentTitle screen={model?.tournament.name ?? title} />
      <h1 className="font-display text-display-section">{title}</h1>
      {model && play ? (
        play.standings.length === 0 ? (
          <p className="text-body-md text-muted-foreground">
            {t("roundRobin.standings.empty")}
          </p>
        ) : (
          <div className="max-w-2xl space-y-3">
            <StandingsTable
              model={model}
              rows={play.standings}
              caption={title}
            />
            <StandingsNotes model={model} rows={play.standings} />
          </div>
        )
      ) : (
        <p role={failed ? "alert" : "status"}>
          {failed ? t("roundRobin.loadFailed") : t("loading")}
        </p>
      )}
    </section>
  );
}
