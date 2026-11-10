import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import type { components } from "@/api/schema";
import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { leagueQueries } from "@/features/leagues/api";
import { setupQueries, tournamentQueries } from "@/features/tournaments/api";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { TournamentItem } from "./setup/TournamentItem";

type TournamentSummary = components["schemas"]["TournamentSummary"];

const byNewest = (a: TournamentSummary, b: TournamentSummary) =>
  b.date.localeCompare(a.date);

/** Screen 1: the season's tournaments, running ones first, and "New tournament" (FR-030, FR-038). */
export function TournamentsPage() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const seasons = useQuery(leagueQueries.seasons(leagueId));
  const seasonId = seasons.data?.find((s) => s.state === "active")?.id;
  const tournaments = useQuery(tournamentQueries.ofSeason(leagueId, seasonId));
  const players = useQuery(setupQueries.players(leagueId));
  const summaries = tournaments.data ?? [];

  const names = new Map(players.data?.map((p) => [p.id, p.name]));
  const nameOf = (playerId: string) => names.get(playerId) ?? "";

  const running = summaries
    .filter((summary) => summary.state !== "finished")
    .sort(
      (a, b) =>
        Number(a.state === "setup") - Number(b.state === "setup") ||
        byNewest(a, b),
    );
  const finished = summaries
    .filter((summary) => summary.state === "finished")
    .sort(byNewest);

  const group = (
    id: string,
    heading: string,
    items: TournamentSummary[],
    wide: boolean,
  ) =>
    items.length === 0 ? null : (
      <section aria-labelledby={id} className="grid gap-3">
        <h2 id={id} className="text-body-sm font-bold text-muted-foreground">
          {heading}
        </h2>
        <ul
          className={
            wide
              ? "grid gap-3 md:grid-cols-2 xl:grid-cols-3"
              : "grid gap-3 md:grid-cols-2"
          }
        >
          {items.map((summary) => (
            <TournamentItem
              key={summary.id}
              leagueId={leagueId}
              summary={summary}
              nameOf={nameOf}
            />
          ))}
        </ul>
      </section>
    );

  return (
    <div className="grid gap-6">
      <DocumentTitle screen={t("tournaments.list.title")} />
      <div className="grid gap-4 md:flex md:items-end md:justify-between">
        <h1 className="font-display text-display-title">
          {t("tournaments.list.title")}
        </h1>
        <Button asChild size="lg" className="md:min-w-60">
          <Link to={generatePath(paths.newTournament, { leagueId })}>
            {t("tournaments.list.newTournament")}
          </Link>
        </Button>
      </div>

      {tournaments.isError && (
        <p role="alert" className="text-body-md text-destructive">
          {t("tournaments.list.error")}
        </p>
      )}
      {tournaments.isPending && (
        <div role="status" className="grid gap-3">
          <span className="sr-only">{t("loading")}</span>
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      )}
      {tournaments.data?.length === 0 && (
        <p className="text-body-md text-muted-foreground">
          {t("tournaments.list.empty")}
        </p>
      )}
      {group("running-heading", t("tournaments.list.running"), running, false)}
      {group(
        "finished-heading",
        t("tournaments.list.finished"),
        finished,
        true,
      )}
    </div>
  );
}
