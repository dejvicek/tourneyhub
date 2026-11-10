import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, NavLink } from "react-router";

import { paths } from "@/lib/paths";

// TODO(foundation-layout): TournamentLayout brings the tournament header and
// its tabs; this stand-in goes with the rebase.
export function TempChrome({
  leagueId,
  tournamentId,
  title,
  subtitle,
  children,
}: {
  leagueId: string;
  tournamentId: string;
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const tabs = [
    {
      to: generatePath(paths.tournament, { leagueId, tournamentId }),
      label: t("roundRobin.tabs.schedule"),
    },
    {
      to: generatePath(paths.fields, { leagueId, tournamentId }),
      label: t("roundRobin.tabs.fields"),
    },
  ];
  return (
    <section className="space-y-5">
      <header className="space-y-1">
        <h1 className="font-display text-display-screen">{title}</h1>
        {subtitle !== undefined && (
          <p className="text-body-md text-muted-foreground">{subtitle}</p>
        )}
      </header>
      <nav aria-label={t("roundRobin.tabs.label")}>
        <ul className="flex gap-1 rounded-lg bg-nav-active p-1">
          {tabs.map((tab) => (
            <li key={tab.to} className="flex-1">
              <NavLink
                to={tab.to}
                end
                className="flex h-11 items-center justify-center rounded-md text-body-sm text-nav-active-foreground aria-[current=page]:bg-card aria-[current=page]:font-bold aria-[current=page]:text-card-foreground"
              >
                {tab.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      {children}
    </section>
  );
}
