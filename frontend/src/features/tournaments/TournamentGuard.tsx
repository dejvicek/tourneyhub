import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Navigate, Outlet, useMatches } from "react-router";

import { ApiError } from "@/api/client";
import { NotFoundPage } from "@/components/NotFoundPage";
import { tournamentQueries } from "@/features/tournaments/api";
import {
  type TournamentScreen,
  tournamentScreens,
} from "@/features/tournaments/tournamentViews";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";
import { tournamentScreenOf } from "@/lib/routeHandle";

function isScreen(
  screens: readonly TournamentScreen[],
  screen: keyof typeof paths | undefined,
): boolean {
  return screens.some((candidate) => candidate === screen);
}

/**
 * The parent of one tournament's screens. An unknown tournament is a
 * not-found page. A screen the tournament's state does not have, such as the
 * end of a round robin that is still running, or a wizard step of a running
 * one, goes to the tournament's own path, which opens the right screen.
 */
export function TournamentGuard() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const screen = tournamentScreenOf(useMatches());

  if (tournament.error instanceof ApiError && tournament.error.status === 404) {
    return <NotFoundPage />;
  }
  if (tournament.data === undefined) {
    return tournament.isError ? (
      <Outlet />
    ) : (
      <p role="status" className="text-body-md text-muted-foreground">
        {t("loading")}
      </p>
    );
  }
  if (
    screen !== undefined &&
    !isScreen(tournamentScreens(tournament.data), screen)
  ) {
    return (
      <Navigate
        replace
        to={generatePath(paths.tournament, { leagueId, tournamentId })}
      />
    );
  }
  return <Outlet />;
}
