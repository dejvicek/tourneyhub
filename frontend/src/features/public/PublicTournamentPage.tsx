import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { PageFallback } from "@/components/PageFallback";
import { Badge } from "@/components/ui/badge";
import type { PlayerRead } from "@/demo/contract";
import { RankingTable } from "@/features/tournaments/finals/RankingTable";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { publicQueries, type PublicTournament } from "./api";
import { LiveFields } from "./LiveFields";
import { PublicKnockout } from "./PublicKnockout";
import { useNames } from "./useNames";

/**
 * The share link's view of one tournament (FR-070): while it runs, the
 * fields, the queue, the standings and the results so far; once finished,
 * the final places and their season points. Read-only (FR-072).
 */
export function PublicTournamentPage() {
  const { t } = useTranslation();
  const shareToken = useRouteParam("shareToken");
  const tournamentId = useRouteParam("tournamentId");
  const league = useQuery(publicQueries.league(shareToken));
  const tournament = useQuery(
    publicQueries.tournament(shareToken, tournamentId),
  );

  if (tournament.isError || league.isError) {
    return (
      <section role="alert" className="space-y-4">
        <DocumentTitle screen={t("publicView.tournament.title")} />
        <h1 className="font-display text-display-title">
          {t("publicView.tournament.title")}
        </h1>
        <p className="text-body-md">{t("publicView.tournament.notFound")}</p>
        <BackLink shareToken={shareToken} league={league.data?.name} />
      </section>
    );
  }
  if (tournament.data === undefined || league.data === undefined) {
    return (
      <>
        <DocumentTitle screen={t("publicView.tournament.title")} />
        <PageFallback />
      </>
    );
  }
  return (
    <TournamentView
      shareToken={shareToken}
      leagueName={league.data.name}
      players={league.data.players}
      tournament={tournament.data}
    />
  );
}

function BackLink({
  shareToken,
  league,
}: {
  shareToken: string;
  league: string | undefined;
}) {
  const { t } = useTranslation();
  return (
    <Link
      to={generatePath(paths.publicLeague, { shareToken })}
      className="inline-flex min-h-11 items-center text-body-md font-bold text-primary underline underline-offset-4"
    >
      {t("publicView.tournament.back", {
        league: league ?? t("publicView.league.title"),
      })}
    </Link>
  );
}

function TournamentView({
  shareToken,
  leagueName,
  players,
  tournament,
}: {
  shareToken: string;
  leagueName: string;
  players: PlayerRead[];
  tournament: PublicTournament;
}) {
  const { t, i18n } = useTranslation();
  const date = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    dateStyle: "full",
  }).format(new Date(`${tournament.date}T12:00:00Z`));
  const running = tournament.state === "in_progress";

  return (
    <section className="space-y-8">
      <DocumentTitle screen={tournament.name} />
      <header className="space-y-2">
        <BackLink shareToken={shareToken} league={leagueName} />
        <p className="flex flex-wrap items-center gap-2 text-body-sm text-muted-foreground">
          <Badge variant={running ? "warning" : "secondary"}>
            {tournament.state === "setup"
              ? null
              : t(`publicView.state.${tournament.state}`)}
          </Badge>
          {t("publicView.tournament.typeAndDate", {
            type: t(`publicView.type.${tournament.type}`),
            date,
          })}
        </p>
        <h1 className="font-display text-display-title break-words">
          {tournament.name}
        </h1>
      </header>
      {running && (
        <section aria-labelledby="fields" className="space-y-3">
          <h2 id="fields" className="sr-only">
            {t("publicView.tournament.fieldsHeading")}
          </h2>
          <LiveFields
            tournament={tournament}
            players={players}
            headingLevel={3}
          />
        </section>
      )}
      {tournament.places !== null && (
        <Places tournament={tournament} players={players} />
      )}
      {tournament.phases.some((phase) => phase.kind === "knockout") && (
        <PublicKnockout
          shareToken={shareToken}
          tournament={tournament}
          players={players}
        />
      )}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-2 lg:items-start">
        <Standings
          shareToken={shareToken}
          tournament={tournament}
          players={players}
        />
        <Results tournament={tournament} players={players} />
      </div>
    </section>
  );
}

/** The design's place rows (screen 10): place, names, points each. */
function Places({
  tournament,
  players,
}: {
  tournament: PublicTournament;
  players: PlayerRead[];
}) {
  const { t } = useTranslation();
  const names = useNames(players, tournament);
  return (
    <section aria-labelledby="places" className="space-y-3">
      <h2 id="places" className="font-display text-display-section">
        {t("publicView.tournament.placesHeading")}
      </h2>
      <ol className="rounded-lg border border-border-surface bg-card px-4 text-card-foreground">
        {(tournament.places ?? []).map((row) => (
          <li
            key={row.entry_id}
            className="flex items-center gap-3 border-t border-border py-3 first:border-t-0"
          >
            <span
              className={
                row.place === 1
                  ? "w-10 shrink-0 font-display text-score-m text-primary"
                  : "w-10 shrink-0 font-display text-score-m"
              }
            >
              {t("publicView.table.placeValue", { place: row.place })}
            </span>
            <span className="min-w-0 flex-1 text-body-md font-bold break-words">
              {names.ofEntry(row.entry_id)}
            </span>
            <span className="text-body-sm font-bold text-primary">
              {t("publicView.tournament.pointsEach", {
                count: row.points_per_player,
              })}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * The group phase's standings: a round robin's table, or the ranking of a
 * Swiss or Monster DYP with its tie-breakers, as the organizer sees it. A
 * knockout-only tournament has none.
 */
function Standings({
  shareToken,
  tournament,
  players,
}: {
  shareToken: string;
  tournament: PublicTournament;
  players: PlayerRead[];
}) {
  const { t } = useTranslation();
  const format = tournament.phases.find(
    (phase) => phase.kind === "group",
  )?.format;
  if (format === undefined) {
    return null;
  }
  return (
    <section aria-labelledby="standings" className="min-w-0 space-y-3">
      <h2 id="standings" className="font-display text-display-section">
        {t("publicView.tournament.standingsHeading")}
      </h2>
      {format === "swiss" || format === "monster_dyp" ? (
        <RankingStandings
          shareToken={shareToken}
          tournament={tournament}
          players={players}
        />
      ) : (
        <TableStandings
          shareToken={shareToken}
          tournament={tournament}
          players={players}
        />
      )}
    </section>
  );
}

function RankingStandings({
  shareToken,
  tournament,
  players,
}: {
  shareToken: string;
  tournament: PublicTournament;
  players: PlayerRead[];
}) {
  const { t } = useTranslation();
  const names = useNames(players, tournament);
  const ranking = useQuery(
    publicQueries.ranking(shareToken, tournament.id, true),
  );
  if (ranking.data === undefined) {
    return (
      <p role="status" className="text-body-md text-muted-foreground">
        {t("loading")}
      </p>
    );
  }
  return (
    <div className="rounded-lg border border-border-surface bg-card px-4 text-card-foreground">
      <RankingTable
        ranking={ranking.data}
        participants={[]}
        entryName={names.ofEntry}
        caption={t("publicView.tournament.standingsHeading")}
      />
    </div>
  );
}

function TableStandings({
  shareToken,
  tournament,
  players,
}: {
  shareToken: string;
  tournament: PublicTournament;
  players: PlayerRead[];
}) {
  const { t, i18n } = useTranslation();
  const names = useNames(players, tournament);
  const standings = useQuery(
    publicQueries.standings(shareToken, tournament.id),
  );
  const signed = new Intl.NumberFormat(i18n.resolvedLanguage, {
    signDisplay: "exceptZero",
  });
  if (standings.data === undefined) {
    return standings.isPending ? (
      <p role="status" className="text-body-md text-muted-foreground">
        {t("loading")}
      </p>
    ) : null;
  }
  return (
    // The table scrolls inside its own box, never the page; a phone drops the
    // score-difference column to keep the names readable.
    <div className="overflow-x-auto rounded-lg border border-border-surface bg-card text-card-foreground">
      <table className="w-full text-left text-body-md">
        <caption className="sr-only">
          {t("publicView.tournament.standingsHeading")}
        </caption>
        <thead className="text-caption text-muted-foreground">
          <tr className="border-b border-border">
            <th scope="col" className="px-3 py-2 font-bold">
              {t("publicView.table.place")}
            </th>
            <th scope="col" className="px-2 py-2 font-bold">
              {t("publicView.table.entry")}
            </th>
            <th scope="col" className="px-2 py-2 text-right font-bold">
              {t("publicView.table.played")}
            </th>
            <th
              scope="col"
              className="hidden px-2 py-2 text-right font-bold sm:table-cell"
            >
              {t("publicView.table.difference")}
            </th>
            <th scope="col" className="px-3 py-2 text-right font-bold">
              {t("publicView.table.points")}
            </th>
          </tr>
        </thead>
        <tbody>
          {standings.data.map((row) => (
            <tr
              key={row.entry_id}
              className="border-b border-border last:border-b-0"
            >
              <td className="px-3 py-2 font-display text-score-m">
                {t("publicView.table.placeValue", { place: row.place })}
              </td>
              <th
                scope="row"
                className="min-w-0 px-2 py-2 font-bold break-words"
              >
                {names.ofEntry(row.entry_id)}
              </th>
              <td className="px-2 py-2 text-right">{row.played}</td>
              <td className="hidden px-2 py-2 text-right text-muted-foreground sm:table-cell">
                {signed.format(row.score_difference)}
              </td>
              <td className="px-3 py-2 text-right font-display text-score-m">
                {row.points}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Played matches by round, newest round first. */
function Results({
  tournament,
  players,
}: {
  tournament: PublicTournament;
  players: PlayerRead[];
}) {
  const { t } = useTranslation();
  const names = useNames(players, tournament);
  const rounds = tournament.rounds
    .map((round) => ({
      ...round,
      played: round.matches.filter((match) => match.outcome !== null),
    }))
    .filter((round) => round.played.length > 0)
    .reverse();

  return (
    <section aria-labelledby="results" className="min-w-0 space-y-3">
      <h2 id="results" className="font-display text-display-section">
        {t("publicView.tournament.resultsHeading")}
      </h2>
      {rounds.length === 0 ? (
        <p className="text-body-md text-muted-foreground">
          {t("publicView.tournament.noResults")}
        </p>
      ) : (
        rounds.map((round) => (
          <section
            key={round.id}
            aria-labelledby={round.id}
            className="space-y-2"
          >
            <h3
              id={round.id}
              className="text-body-sm font-bold text-muted-foreground"
            >
              {t("publicView.tournament.round", { number: round.round_no })}
            </h3>
            <ul className="rounded-lg border border-border-surface bg-card px-4 text-card-foreground">
              {round.played.map((match) => {
                const bye = match.sides.find((side) => side.is_bye);
                if (bye !== undefined) {
                  // An entry with no opponent goes through; it is not a match.
                  const entry = match.sides.find((side) => !side.is_bye);
                  return (
                    <li
                      key={match.id}
                      className="border-t border-border py-2.5 text-body-sm break-words text-muted-foreground first:border-t-0"
                    >
                      {t("publicView.match.bye", {
                        name: names.ofPlayers(entry?.player_ids ?? []),
                      })}
                    </li>
                  );
                }
                // BO1: the goals; best-of: the games won (BR-120).
                const score =
                  match.games.length === 1
                    ? {
                        a: match.games[0]?.score_1 ?? 0,
                        b: match.games[0]?.score_2 ?? 0,
                      }
                    : {
                        a: match.games.filter((g) => g.winner === "side_1")
                          .length,
                        b: match.games.filter((g) => g.winner === "side_2")
                          .length,
                      };
                return (
                  <li
                    key={match.id}
                    className="flex items-center justify-between gap-3 border-t border-border py-2.5 first:border-t-0"
                  >
                    <span className="min-w-0 text-body-sm break-words">
                      <span
                        className={
                          match.outcome === "side_1" ? "font-bold" : undefined
                        }
                      >
                        {names.ofPlayers(match.sides[0]?.player_ids ?? [])}
                      </span>
                      {t("publicView.match.separator")}
                      <span
                        className={
                          match.outcome === "side_2" ? "font-bold" : undefined
                        }
                      >
                        {names.ofPlayers(match.sides[1]?.player_ids ?? [])}
                      </span>
                    </span>
                    <span className="shrink-0 font-display text-score-s">
                      {match.is_walkover
                        ? t("publicView.match.walkover")
                        : t("publicView.match.score", score)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
    </section>
  );
}
