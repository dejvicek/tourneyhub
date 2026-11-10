import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link, NavLink, Outlet, useParams } from "react-router";

import { Button } from "@/components/ui/button";
import { ChevronDownIcon } from "@/components/ui/icons";
import { tournamentQueries } from "@/features/tournaments/api";
import { tournamentTabs } from "@/features/tournaments/tournamentViews";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

/**
 * The frame of one tournament and of its setup wizard (Figma 2–13): back to
 * the list, the tournament's name and the tabs for its format and state.
 * The wizard has no tabs. On a phone it replaces the league's header and
 * bottom bar, which LeagueShell hides here (src/lib/routeHandle.ts).
 */
export function TournamentLayout() {
  const { t } = useTranslation();
  const { tournamentId } = useParams();

  return (
    <div className="space-y-6">
      {tournamentId === undefined ? (
        <TournamentHeader name={t("tournaments.list.newTournament")} />
      ) : (
        <ExistingTournamentHeader tournamentId={tournamentId} />
      )}
      <Outlet />
    </div>
  );
}

function ExistingTournamentHeader({ tournamentId }: { tournamentId: string }) {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const tabs =
    tournament.data === undefined ? [] : tournamentTabs(tournament.data);

  return (
    <TournamentHeader name={tournament.data?.name}>
      {tabs.length > 0 && (
        <nav
          aria-label={t("tournaments.header.tabs")}
          className="overflow-x-auto"
        >
          <ul className="flex gap-1 border-b">
            {tabs.map((tab) => (
              <li key={tab.path}>
                <NavLink
                  to={generatePath(paths[tab.path], { leagueId, tournamentId })}
                  className="inline-flex min-h-11 items-center border-b-2 border-transparent px-3 text-body-sm font-bold whitespace-nowrap text-muted-foreground aria-[current=page]:border-primary aria-[current=page]:text-foreground"
                >
                  {t(`tournaments.tabs.${tab.label}`)}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </TournamentHeader>
  );
}

function TournamentHeader({
  name,
  children,
}: {
  name: string | undefined;
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Button asChild variant="ghost" size="icon">
          <Link
            to={generatePath(paths.tournaments, { leagueId })}
            aria-label={t("tournaments.header.back")}
          >
            <ChevronDownIcon className="rotate-90" />
          </Link>
        </Button>
        <p className="min-w-0 font-display text-display-name break-words">
          {name}
        </p>
      </div>
      {children}
    </div>
  );
}
