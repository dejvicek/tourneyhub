import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link, Outlet } from "react-router";

import { PlaceholderPage } from "@/components/PlaceholderPage";
import { tournamentQueries } from "@/features/tournaments/api";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

// The tournament screens reached from here, until the real screens link them.
const TOURNAMENT_SCREENS = [
  { path: paths.setupPlayers, title: "tournaments.setupPlayers.title" },
  { path: paths.setupDraw, title: "tournaments.setupDraw.title" },
  { path: paths.setupReview, title: "tournaments.setupReview.title" },
  { path: paths.fields, title: "fields.now.title" },
  { path: paths.editFields, title: "fields.edit.title" },
  { path: paths.tournamentStandings, title: "tournaments.standings.title" },
  { path: paths.groupPhaseDone, title: "tournaments.groupPhaseDone.title" },
  { path: paths.knockout, title: "tournaments.knockout.title" },
  { path: paths.finished, title: "tournaments.finished.title" },
  { path: paths.betweenRounds, title: "tournaments.betweenRounds.title" },
  { path: paths.lateAndDisabled, title: "tournaments.lateAndDisabled.title" },
  { path: paths.startKnockout, title: "tournaments.startKnockout.title" },
] as const;

const MATCH_SCREENS = [
  { path: paths.scheduleResult, title: "results.enter.title" },
  { path: paths.moveMatch, title: "fields.move.title" },
] as const;

const linkClass =
  "inline-flex min-h-11 items-center underline-offset-4 hover:underline";

// Placeholder (FR-035, FR-060, BR-050–BR-054). The result overlay opens
// over it (<Outlet />).
export function RoundRobinPage() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const matchId = tournament.data?.waiting[0];

  return (
    <PlaceholderPage screen="6" title={t("tournaments.roundRobin.title")}>
      <nav aria-label={t("tournaments.roundRobin.screens")}>
        <ul>
          {TOURNAMENT_SCREENS.map((screen) => (
            <li key={screen.path}>
              <Link
                to={generatePath(screen.path, { leagueId, tournamentId })}
                className={linkClass}
              >
                {t(screen.title)}
              </Link>
            </li>
          ))}
          {matchId !== undefined &&
            MATCH_SCREENS.map((screen) => (
              <li key={screen.path}>
                <Link
                  to={generatePath(screen.path, {
                    leagueId,
                    tournamentId,
                    matchId,
                  })}
                  className={linkClass}
                >
                  {t(screen.title)}
                </Link>
              </li>
            ))}
        </ul>
      </nav>
      <Outlet />
    </PlaceholderPage>
  );
}
