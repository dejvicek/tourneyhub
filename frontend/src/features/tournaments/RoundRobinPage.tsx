import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { FieldsStrip } from "./play/FieldsStrip";
import { groupProgress } from "./play/model";
import { Notice } from "./play/Notice";
import { ProgressLine } from "./play/ProgressLine";
import { ScheduleView } from "./play/ScheduleView";
import { StandingsPanel } from "./play/StandingsPanel";
import { TempChrome } from "./play/TempChrome";
import { useEntryCount } from "./play/useEntryNoun";
import { usePlay } from "./play/usePlay";

/**
 * Screen 6: the running round robin. Progress, who is on which field, the
 * schedule by round with results, and the live standings beside it from
 * the tablet up (FR-035, FR-060, FR-092, BR-050–BR-053).
 */
export function RoundRobinPage() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const { model, play, failed } = usePlay(leagueId, tournamentId);
  const entryCount = useEntryCount();
  const params = { leagueId, tournamentId };

  if (!model) {
    return (
      <>
        <DocumentTitle screen={t("tournaments.roundRobin.title")} />
        <p role={failed ? "alert" : "status"}>
          {failed ? t("roundRobin.loadFailed") : t("loading")}
        </p>
      </>
    );
  }
  const { tournament } = model;
  const progress = groupProgress(model);

  return (
    <TempChrome
      leagueId={leagueId}
      tournamentId={tournamentId}
      title={tournament.name}
      subtitle={t("roundRobin.subtitle", {
        entries: entryCount(tournament.type, tournament.entries.length),
      })}
    >
      <DocumentTitle screen={tournament.name} />
      <ProgressLine progress={progress} />
      {play?.group_done === true && tournament.state === "in_progress" && (
        <Notice variant="info" title={t("roundRobin.done.title")}>
          <Link
            to={generatePath(paths.groupPhaseDone, params)}
            className="inline-flex min-h-11 items-center font-bold underline underline-offset-4"
          >
            {t("roundRobin.done.link")}
          </Link>
        </Notice>
      )}
      <FieldsStrip
        model={model}
        manageHref={generatePath(paths.editFields, params)}
      />
      <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,20rem)] lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        <section aria-labelledby="schedule" className="space-y-3">
          <h2 id="schedule" className="font-display text-display-section">
            {t("roundRobin.schedule.title")}
          </h2>
          <ScheduleView
            model={model}
            resultHref={(matchId) =>
              generatePath(paths.enterResult, { ...params, matchId })
            }
          />
        </section>
        <aside className="hidden md:block">
          <StandingsPanel model={model} play={play} />
        </aside>
      </div>
    </TempChrome>
  );
}
