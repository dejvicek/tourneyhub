import { useTranslation } from "react-i18next";
import { generatePath, NavLink } from "react-router";

import { paths } from "@/lib/paths";

// The league's four sections (Figma: app shell). The phone's bottom bar and
// the tablet's tabs use the short labels, the desktop sidebar the long ones.
const SECTIONS = [
  {
    path: paths.tournaments,
    short: "shell.nav.tournaments",
    long: "shell.nav.tournaments",
  },
  {
    path: paths.seasonStandings,
    short: "shell.nav.standings",
    long: "shell.nav.seasonStandings",
  },
  {
    path: paths.players,
    short: "shell.nav.players",
    long: "shell.nav.players",
  },
  {
    path: paths.leagueSettings,
    short: "shell.nav.league",
    long: "shell.nav.leagueSettings",
  },
] as const;

const STYLES = {
  // Fixed to the bottom, above the home indicator (WCAG 2.5.8; 56 px targets).
  bottom: {
    nav: "fixed inset-x-0 bottom-0 z-10 border-t bg-nav pb-[env(safe-area-inset-bottom)]",
    list: "grid h-bottom-bar grid-cols-4 gap-1 px-2 pt-2 pb-3",
    link: "flex h-full items-center justify-center rounded-sm px-1 text-center text-caption font-bold text-nav-foreground aria-[current=page]:bg-nav-active aria-[current=page]:text-nav-active-foreground",
  },
  tabs: {
    nav: "px-2",
    list: "flex gap-1",
    link: "inline-flex min-h-11 items-center border-b-2 border-transparent px-3 text-body-sm font-bold text-muted-foreground aria-[current=page]:border-primary aria-[current=page]:text-foreground",
  },
  sidebar: {
    nav: "",
    list: "flex flex-col gap-1",
    link: "flex min-h-11 items-center rounded-sm px-3 text-body-md text-sidebar-foreground hover:bg-sidebar-accent aria-[current=page]:bg-sidebar-accent aria-[current=page]:font-bold aria-[current=page]:text-sidebar-accent-foreground",
  },
} as const satisfies Record<
  string,
  { nav: string; list: string; link: string }
>;

interface LeagueNavProps {
  leagueId: string;
  variant: keyof typeof STYLES;
}

/** The league's main navigation in one of its three layouts. */
export function LeagueNav({ leagueId, variant }: LeagueNavProps) {
  const { t } = useTranslation();
  const style = STYLES[variant];

  return (
    <nav aria-label={t("shell.nav.label")} className={style.nav}>
      <ul className={style.list}>
        {SECTIONS.map((section) => (
          <li key={section.path}>
            <NavLink
              to={generatePath(section.path, { leagueId })}
              className={style.link}
            >
              {t(variant === "sidebar" ? section.long : section.short)}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
