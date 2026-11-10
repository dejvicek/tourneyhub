import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { PlaceholderPage } from "@/components/PlaceholderPage";
import { leagueQueries } from "@/features/leagues/api";
import { useSeasonName } from "@/features/leagues/useSeasonName";
import { paths } from "@/lib/paths";

// Placeholder (FR-007), with links into each league so the demo is clickable.
export function MyLeaguesPage() {
  const { t } = useTranslation();
  const seasonName = useSeasonName();
  const leagues = useQuery(leagueQueries.list());

  return (
    <PlaceholderPage title={t("leagues.myLeagues.title")}>
      {leagues.data?.length === 0 && <p>{t("leagues.myLeagues.empty")}</p>}
      <ul className="space-y-2">
        {leagues.data?.map((league) => (
          <li key={league.id}>
            <Link
              to={generatePath(paths.tournaments, { leagueId: league.id })}
              className="flex min-h-11 flex-col justify-center rounded-lg border bg-card px-4 py-2 text-card-foreground"
            >
              <span className="text-body-md font-bold">{league.name}</span>
              <span className="text-caption text-muted-foreground">
                {seasonName(league.active_season)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </PlaceholderPage>
  );
}
