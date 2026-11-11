import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { PageFallback } from "@/components/PageFallback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  SeasonRead,
  SeasonStandingRow,
  TournamentSummary,
} from "@/demo/contract";
import { EmptyState } from "@/features/leagues/EmptyState";
import { useSeasonName } from "@/features/leagues/useSeasonName";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { type PublicLeague, type PublicPlayer, publicQueries } from "./api";
import { LiveFields } from "./LiveFields";
import { useNames } from "./useNames";

/**
 * The share link's view of a league (FR-070–FR-072), for players and
 * spectators without an account: no organizer navigation, nothing to change.
 * The running tournaments with their fields come first, then the season
 * standings and the finished tournaments. Tournaments in setup never appear.
 */
export function PublicLeaguePage() {
  const { t } = useTranslation();
  const shareToken = useRouteParam("shareToken");
  const league = useQuery(publicQueries.league(shareToken));

  if (league.isPending) {
    return (
      <>
        <DocumentTitle screen={t("publicView.league.title")} />
        <PageFallback />
      </>
    );
  }
  if (league.isError) {
    return (
      <section role="alert" className="space-y-4">
        <DocumentTitle screen={t("publicView.league.title")} />
        <h1 className="font-display text-display-title">
          {t("publicView.league.title")}
        </h1>
        <p className="text-body-md">{t("publicView.league.notFound")}</p>
      </section>
    );
  }
  return <LeagueView shareToken={shareToken} league={league.data} />;
}

function LeagueView({
  shareToken,
  league,
}: {
  shareToken: string;
  league: PublicLeague;
}) {
  const { t } = useTranslation();
  const seasonName = useSeasonName();
  const active = league.seasons.find((season) => season.state === "active");

  return (
    <section className="space-y-8">
      <DocumentTitle screen={league.name} />
      <header className="space-y-2">
        <p className="text-body-sm font-bold text-muted-foreground">
          {active === undefined
            ? t("publicView.kicker")
            : t("publicView.kickerSeason", { season: seasonName(active) })}
        </p>
        <h1 className="font-display text-display-title break-words">
          {league.name}
        </h1>
        <p className="text-caption text-muted-foreground">
          {t("publicView.league.refreshed")}
        </p>
      </header>
      {active !== undefined && (
        <SeasonView
          shareToken={shareToken}
          season={active}
          players={league.players}
        />
      )}
    </section>
  );
}

/** The active season: its running tournaments, standings and finished ones. */
function SeasonView({
  shareToken,
  season,
  players,
}: {
  shareToken: string;
  season: SeasonRead;
  players: PublicPlayer[];
}) {
  const { t } = useTranslation();
  const tournaments = useQuery(
    publicQueries.tournaments(shareToken, season.id),
  );
  const standings = useQuery(
    publicQueries.seasonStandings(shareToken, season.id),
  );
  if (tournaments.data === undefined) {
    return tournaments.isPending ? (
      <PageFallback />
    ) : (
      <p role="alert" className="text-body-md">
        {t("publicView.tournament.loadFailed")}
      </p>
    );
  }
  // Newest first, as the API lists them.
  const running = tournaments.data.filter((x) => x.state === "in_progress");
  const finished = tournaments.data.filter((x) => x.state === "finished");

  return (
    <>
      <section aria-labelledby="live" className="space-y-3">
        <h2 id="live" className="font-display text-display-section">
          {t("publicView.league.liveHeading")}
        </h2>
        {running.length === 0 ? (
          <p className="text-body-md text-muted-foreground">
            {t("publicView.league.noLive")}
          </p>
        ) : (
          running.map((tournament) => (
            <LiveTournament
              key={tournament.id}
              shareToken={shareToken}
              summary={tournament}
              players={players}
            />
          ))
        )}
      </section>

      <section aria-labelledby="standings" className="space-y-3">
        <h2 id="standings" className="font-display text-display-section">
          {t("publicView.league.standingsHeading")}
        </h2>
        {standings.data === undefined || standings.data.length === 0 ? (
          <EmptyState title={t("publicView.league.noStandings")} />
        ) : (
          <SeasonStandings rows={standings.data} players={players} />
        )}
      </section>

      <section aria-labelledby="finished" className="space-y-3">
        <h2 id="finished" className="font-display text-display-section">
          {t("publicView.league.finishedHeading")}
        </h2>
        {finished.length === 0 ? (
          <p className="text-body-md text-muted-foreground">
            {t("publicView.league.noFinished")}
          </p>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {finished.map((tournament) => (
              <li key={tournament.id}>
                <TournamentLink shareToken={shareToken} summary={tournament} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function useDate() {
  const { i18n } = useTranslation();
  const format = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  // A calendar date: read it at noon UTC so no time zone moves the day.
  return (date: string) => format.format(new Date(`${date}T12:00:00Z`));
}

/** The design's tournament item: state dot, title, type and date. */
function TournamentLink({
  shareToken,
  summary,
}: {
  shareToken: string;
  summary: TournamentSummary;
}) {
  const { t } = useTranslation();
  const date = useDate();
  return (
    <Link
      to={generatePath(paths.publicTournament, {
        shareToken,
        tournamentId: summary.id,
      })}
      className="block min-h-11 space-y-1 rounded-lg border border-border-surface bg-card px-4 py-3.5 text-card-foreground hover:border-primary focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-hidden"
    >
      <span className="flex items-center justify-between gap-2 text-caption">
        <span className="flex items-center gap-2 font-bold">
          <span
            aria-hidden="true"
            className="size-2.5 rounded-full bg-foreground"
          />
          {t("publicView.state.finished")}
        </span>
        <span className="text-muted-foreground">{date(summary.date)}</span>
      </span>
      <span className="block font-display text-display-name break-words">
        {summary.name}
      </span>
      <span className="block text-body-sm text-muted-foreground">
        {t(`publicView.type.${summary.type}`)}
      </span>
    </Link>
  );
}

/** A running tournament with its fields and queue (FR-070, FR-092). */
function LiveTournament({
  shareToken,
  summary,
  players,
}: {
  shareToken: string;
  summary: TournamentSummary;
  players: PublicPlayer[];
}) {
  const { t } = useTranslation();
  const date = useDate();
  const tournament = useQuery(publicQueries.tournament(shareToken, summary.id));
  const headingId = `live-${summary.id}`;

  return (
    <article
      aria-labelledby={headingId}
      className="space-y-4 rounded-lg border-2 border-team-a bg-card p-4 text-card-foreground"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="flex items-center gap-2 text-caption font-bold">
            <span
              aria-hidden="true"
              className="size-2.5 rounded-full bg-team-a"
            />
            {t("publicView.state.in_progress")}
            <span className="font-normal text-muted-foreground">
              {date(summary.date)}
            </span>
          </p>
          <h3 id={headingId} className="font-display text-display-name">
            {summary.name}
          </h3>
          <Badge variant="secondary">
            {t(`publicView.type.${summary.type}`)}
          </Badge>
        </div>
        <Button asChild>
          <Link
            to={generatePath(paths.publicTournament, {
              shareToken,
              tournamentId: summary.id,
            })}
          >
            {t("publicView.league.open", { name: summary.name })}
          </Link>
        </Button>
      </header>
      {tournament.data === undefined ? (
        tournament.isPending ? (
          <PageFallback />
        ) : null
      ) : (
        <LiveFields
          tournament={tournament.data}
          players={players}
          headingLevel={3}
        />
      )}
    </article>
  );
}

/** FR-070: the active season's standings, as a table that may scroll. */
function SeasonStandings({
  rows,
  players,
}: {
  rows: SeasonStandingRow[];
  players: PublicPlayer[];
}) {
  const { t } = useTranslation();
  const names = useNames(players);

  return (
    <div className="overflow-x-auto rounded-lg border border-border-surface bg-card text-card-foreground">
      <table className="w-full text-left text-body-md">
        <thead className="text-caption text-muted-foreground">
          <tr className="border-b border-border">
            <th scope="col" className="px-4 py-2 font-bold">
              {t("publicView.table.place")}
            </th>
            <th scope="col" className="px-2 py-2 font-bold">
              {t("publicView.table.player")}
            </th>
            <th scope="col" className="px-2 py-2 text-right font-bold">
              {t("publicView.table.tournaments")}
            </th>
            <th scope="col" className="px-2 py-2 text-right font-bold">
              {t("publicView.table.wins")}
            </th>
            <th scope="col" className="px-4 py-2 text-right font-bold">
              {t("publicView.table.points")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.player_id}
              className="border-b border-border last:border-b-0"
            >
              <td
                className={
                  row.place === 1
                    ? "px-4 py-2 font-display text-score-m text-primary"
                    : "px-4 py-2 font-display text-score-m"
                }
              >
                {t("publicView.table.placeValue", { place: row.place })}
              </td>
              <th scope="row" className="px-2 py-2 font-bold">
                {names.ofPlayers([row.player_id])}
              </th>
              <td className="px-2 py-2 text-right">{row.tournaments_played}</td>
              <td className="px-2 py-2 text-right">{row.tournament_wins}</td>
              <td className="px-4 py-2 text-right font-display text-score-m">
                {row.points}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
