import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Navigate } from "react-router";

import { tournamentQueries } from "@/features/tournaments/api";
import { tournamentHome } from "@/features/tournaments/tournamentViews";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

/** The tournament's own path: goes on to the screen for its state and phase. */
export function TournamentRedirect() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));

  if (tournament.isError) {
    throw tournament.error;
  }
  if (tournament.data === undefined) {
    return (
      <p role="status" className="text-body-md text-muted-foreground">
        {t("loading")}
      </p>
    );
  }
  return (
    <Navigate
      replace
      to={generatePath(paths[tournamentHome(tournament.data)], {
        leagueId,
        tournamentId,
      })}
    />
  );
}
