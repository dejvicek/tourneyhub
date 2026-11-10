import { useQuery } from "@tanstack/react-query";
import { cn } from "cn";
import { useTranslation } from "react-i18next";
import { Link, Outlet } from "react-router";

import { DemoNotice } from "@/components/DemoNotice";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { LeagueNav } from "@/components/LeagueNav";
import { authQueries } from "@/features/auth/api";
import { leagueQueries } from "@/features/leagues/api";
import { CopyShareLink } from "@/features/leagues/CopyShareLink";
import { useSeasonName } from "@/features/leagues/useSeasonName";
import { useLayout } from "@/hooks/useLayout";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

/**
 * The organizer's shell inside a league (Figma: app shell). Phone: the league
 * and season on top, a bottom bar with the four sections. Tablet: the same
 * header with tabs. Desktop: a sidebar with the league switcher, the
 * sections, "Copy share link" and the user. The language switch stays in the
 * header, as everywhere else.
 */
export function LeagueShell() {
  const { t } = useTranslation();
  const layout = useLayout();
  const leagueId = useRouteParam("leagueId");
  const seasonName = useSeasonName();
  const league = useQuery(leagueQueries.detail(leagueId));
  const seasons = useQuery(leagueQueries.seasons(leagueId));
  const active = seasons.data?.find((season) => season.state === "active");
  const leagueName = league.data?.name;
  const activeName = active === undefined ? undefined : seasonName(active);

  if (layout === "desktop") {
    return (
      <div className="flex min-h-dvh">
        <header className="sticky top-0 flex h-dvh w-72 shrink-0 flex-col gap-6 border-r border-sidebar-border bg-sidebar p-4 text-sidebar-foreground">
          <div className="flex items-center justify-between gap-2">
            <Link to={paths.home} className="font-display text-display-section">
              {t("app.name")}
            </Link>
            <LanguageSwitch />
          </div>
          <Link
            to={paths.myLeagues}
            className="block rounded-lg border border-sidebar-border px-3 py-2 hover:bg-sidebar-accent"
          >
            <span className="block text-body-md font-bold">{leagueName}</span>
            <span className="block text-caption text-muted-foreground">
              {activeName}
            </span>
            <span className="block text-caption text-muted-foreground">
              {t("shell.switchLeague")}
            </span>
          </Link>
          <LeagueNav leagueId={leagueId} variant="sidebar" />
          <div className="mt-auto space-y-3">
            <CopyShareLink leagueId={leagueId} />
            <UserName />
          </div>
        </header>
        <main className="min-w-0 flex-1 space-y-6 px-8 py-6">
          <DemoNotice />
          <Outlet />
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b bg-nav">
        <div className="flex items-center justify-between gap-4 px-4 py-3">
          <Link
            to={paths.myLeagues}
            className="min-w-0 font-display text-display-section break-words"
          >
            {leagueName !== undefined && activeName !== undefined
              ? t("shell.leagueContext", {
                  league: leagueName,
                  season: activeName,
                })
              : t("app.name")}
          </Link>
          <LanguageSwitch />
        </div>
        {layout === "tablet" && (
          <LeagueNav leagueId={leagueId} variant="tabs" />
        )}
      </header>
      <main
        className={cn(
          "flex-1 space-y-6 px-4 py-6",
          layout === "phone" &&
            "pb-[calc(var(--spacing-bottom-bar)+env(safe-area-inset-bottom)+1.5rem)]",
        )}
      >
        <DemoNotice />
        <Outlet />
      </main>
      {layout === "phone" && <LeagueNav leagueId={leagueId} variant="bottom" />}
    </div>
  );
}

function UserName() {
  const { t } = useTranslation();
  const me = useQuery(authQueries.me());

  if (me.data === undefined) {
    return null;
  }
  return (
    <p className="text-caption text-muted-foreground">
      {t("shell.signedInAs", { name: me.data.display_name })}
    </p>
  );
}
