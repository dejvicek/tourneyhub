import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { PlaceholderPage } from "@/components/PlaceholderPage";
import { leagueQueries } from "@/features/leagues/api";
import { tournamentQueries } from "@/features/tournaments/api";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

// Placeholder (FR-022, FR-030), with links into each tournament so the demo
// is clickable.
export function TournamentsPage() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const seasons = useQuery(leagueQueries.seasons(leagueId));
  const seasonId = seasons.data?.find((s) => s.state === "active")?.id;
  const tournaments = useQuery(tournamentQueries.ofSeason(leagueId, seasonId));

  return (
    <PlaceholderPage screen="1" title={t("tournaments.list.title")}>
      <Link
        to={generatePath(paths.newTournament, { leagueId })}
        className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-button-sm text-primary-foreground"
      >
        {t("tournaments.list.newTournament")}
      </Link>
      {tournaments.data?.length === 0 && <p>{t("tournaments.list.empty")}</p>}
      <ul className="space-y-2">
        {tournaments.data?.map((tournament) => (
          <li key={tournament.id}>
            <Link
              to={generatePath(paths.tournament, {
                leagueId,
                tournamentId: tournament.id,
              })}
              className="flex min-h-11 flex-col justify-center rounded-lg border bg-card px-4 py-2 text-card-foreground"
            >
              <span className="text-body-md font-bold">{tournament.name}</span>
              <span className="text-caption text-muted-foreground">
                {t(`tournaments.state.${tournament.state}`)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </PlaceholderPage>
  );
}
