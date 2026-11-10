import { useTranslation } from "react-i18next";
import { generatePath, Link, Outlet } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { FieldsStrip } from "./play/FieldsStrip";
import { groupProgress } from "./play/model";
import { Notice } from "./play/Notice";
import { ProgressLine } from "./play/ProgressLine";
import { ScheduleView } from "./play/ScheduleView";
import { StandingsPanel } from "./play/StandingsPanel";
import { useEntryCount } from "./play/useEntryNoun";
import { usePlay } from "./play/usePlay";

/**
 * Screen 6: the running round robin. Progress, who is on which field, the
 * schedule by round with results, and the live standings beside it from
 * the tablet up (FR-035, FR-060, FR-092, BR-050–BR-053). Result entry opens
 * over it (<Outlet />). TournamentLayout shows the name and the tabs.
 */
export function RoundRobinPage() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const { model, play, failed } = usePlay(leagueId, tournamentId);
  const entryCount = useEntryCount();
  const params = { leagueId, tournamentId };
  const title = t("tournaments.roundRobin.title");

  return (
    <section className="space-y-6">
      <DocumentTitle screen={model?.tournament.name ?? title} />
      <div>
        <h1 className="sr-only">{title}</h1>
        {model && (
          <p className="text-body-md text-muted-foreground">
            {t("roundRobin.subtitle", {
              entries: entryCount(
                model.tournament.type,
                model.tournament.entries.length,
              ),
            })}
          </p>
        )}
      </div>
      {model ? (
        <>
          <ProgressLine progress={groupProgress(model)} />
          {play?.group_done === true &&
            model.tournament.state === "in_progress" && (
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
                  generatePath(paths.scheduleResult, { ...params, matchId })
                }
              />
            </section>
            <aside className="hidden md:block">
              <StandingsPanel model={model} play={play} />
            </aside>
          </div>
        </>
      ) : (
        <p role={failed ? "alert" : "status"}>
          {failed ? t("roundRobin.loadFailed") : t("loading")}
        </p>
      )}
      <Outlet />
    </section>
  );
}
