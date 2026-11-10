import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";
import { finalsQueries } from "@/features/finals/api";
import { leagueQueries } from "@/features/leagues/api";
import { CopyShareLink } from "@/features/leagues/CopyShareLink";
import { useSeasonName } from "@/features/leagues/useSeasonName";
import { tournamentQueries } from "@/features/tournaments/api";
import { useLayout } from "@/hooks/useLayout";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { localDate, useRoster } from "./finals/names";
import { Notice } from "./finals/Notice";
import { PlaceRows } from "./finals/PlaceRows";
import { ScreenHeader } from "./finals/ScreenHeader";
import { LoadError, Loading } from "./finals/StateMessage";

/** Screen 10: a finished tournament (BR-100–BR-104, BR-110, BR-111). */
export function FinishedPage() {
  const { t } = useTranslation();
  return (
    <div className="space-y-6">
      <DocumentTitle screen={t("finals.finished.title")} />
      <ScreenHeader title={t("finals.finished.title")} />
      <FinishedContent />
    </div>
  );
}

function FinishedContent() {
  const { t, i18n } = useTranslation();
  const layout = useLayout();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const places = useQuery(finalsQueries.places(leagueId, tournamentId));
  const effect = useQuery(finalsQueries.seasonEffect(leagueId, tournamentId));
  const seasons = useQuery(leagueQueries.seasons(leagueId));
  const seasonName = useSeasonName();
  const roster = useRoster(leagueId, tournament.data?.entries);

  if (tournament.isError || places.isError) {
    return (
      <LoadError
        onRetry={() => {
          void tournament.refetch();
          void places.refetch();
        }}
      />
    );
  }
  const data = tournament.data;
  const result = places.data;
  if (data === undefined || result === undefined) {
    return <Loading />;
  }
  if (!result.complete) {
    return (
      <div className="space-y-4">
        <Notice tone="info" title={t("finals.common.notReady")} />
        <Button asChild>
          <Link to={generatePath(paths.tournament, { leagueId, tournamentId })}>
            {data.name}
          </Link>
        </Button>
      </div>
    );
  }

  const season = seasons.data?.find((s) => s.id === data.season_id);
  const entryOf = (entryId: string) =>
    data.entries.find((e) => e.id === entryId);
  const isPair = (entryId: string) =>
    (entryOf(entryId)?.player_ids.length ?? 1) > 1;
  const winners = result.rows.filter((row) => row.place === 1);
  const first = winners[0];
  const points = season?.placement_points ?? [];
  const list = new Intl.ListFormat(i18n.resolvedLanguage, {
    style: "short",
    type: "unit",
  });
  const players = new Map(
    (effect.data ?? []).map((row) => [row.player_id, row] as const),
  );
  const standings = effect.data ?? [];
  const shown = standings.slice(0, 6);
  const playerNames = roster.player;

  const earn =
    first === undefined
      ? null
      : isPair(first.entry_id)
        ? t("finals.finished.earnsEach", { count: first.points_per_player })
        : t("finals.finished.earnsOwn", { count: first.points_per_player });
  const how =
    first === undefined
      ? null
      : first.reason.kind === "won_final"
        ? t("finals.finished.wonFinal", {
            score:
              first.reason.score === null
                ? ""
                : `${String(first.reason.score[0])}:${String(first.reason.score[1])}`,
            opponent: roster.entry(first.reason.opponent_entry_id),
          })
        : t("finals.finished.wonStandings");

  const placesSection = (
    <section aria-labelledby="final-places" className="space-y-3">
      <h2 id="final-places" className="font-display text-display-section">
        {t("finals.finished.places")}
      </h2>
      <PlaceRows
        rows={result.rows}
        entryName={(entryId) => roster.entry(entryId)}
        isPair={isPair}
      />
      <p className="text-caption text-muted-foreground">
        {t("finals.finished.pointsNote", {
          points: list.format(points.map(String)),
        })}
      </p>
    </section>
  );

  const seasonSection = (
    <section aria-labelledby="season-after" className="space-y-3">
      <div>
        <h2 id="season-after" className="font-display text-display-section">
          {t("finals.finished.seasonTitle", {
            season: season === undefined ? "" : seasonName(season),
          })}
        </h2>
        <p className="text-body-sm text-muted-foreground">
          {t("finals.finished.seasonLead", {
            shown: shown.length,
            total: standings.length,
          })}
        </p>
      </div>
      <ol
        aria-label={t("finals.finished.seasonList")}
        className="divide-y divide-border border-t border-b border-border"
      >
        {shown.map((row) => {
          const moved =
            row.previous_place === null ? 0 : row.previous_place - row.place;
          const earned = players.get(row.player_id)?.earned ?? 0;
          const change =
            earned === 0 && moved === 0
              ? ""
              : moved > 0
                ? t("finals.finished.changeUp", {
                    points: t("finals.finished.changePoints", {
                      points: earned,
                    }),
                    count: moved,
                  })
                : moved < 0
                  ? t("finals.finished.changeDown", {
                      points: t("finals.finished.changePoints", {
                        points: earned,
                      }),
                      count: -moved,
                    })
                  : t("finals.finished.changePoints", { points: earned });
          return (
            <li
              key={row.player_id}
              className="grid grid-cols-[2.5rem_minmax(0,1fr)_auto_3rem] items-center gap-x-3 py-2.5"
            >
              <span className="font-display text-score-m">{row.place}</span>
              <span className="text-body-md font-bold">
                {playerNames(row.player_id)}
              </span>
              <span className="text-body-sm text-muted-foreground">
                {change}
              </span>
              <span className="text-end font-display text-score-l">
                {row.points}
              </span>
            </li>
          );
        })}
      </ol>
      <Link
        to={generatePath(paths.seasonStandings, { leagueId })}
        className="inline-flex min-h-11 items-center text-body-md font-bold text-primary underline underline-offset-4"
      >
        {t("finals.finished.seasonFull")}
      </Link>
    </section>
  );

  return (
    <div className="space-y-6">
      <p className="text-body-md text-muted-foreground">
        {t("finals.common.date", { date: localDate(data.date) })}
      </p>
      <section
        aria-labelledby="winners"
        className="space-y-1 rounded-lg border border-border-surface bg-card p-4 text-card-foreground"
      >
        <h2
          id="winners"
          className="text-caption font-bold text-muted-foreground"
        >
          {t("finals.finished.winners")}
        </h2>
        {winners.map((row) => (
          <p
            key={row.entry_id}
            className="font-display text-display-name break-words"
          >
            {roster.entry(row.entry_id)}
          </p>
        ))}
        <p className="text-body-md">{how}</p>
        <p className="text-body-md">{earn}</p>
      </section>
      {layout === "desktop" ? (
        <div className="grid grid-cols-2 gap-8">
          {placesSection}
          {seasonSection}
        </div>
      ) : (
        <>
          {placesSection}
          {seasonSection}
        </>
      )}
      <div className="max-w-sm space-y-3">
        <CopyShareLink leagueId={leagueId} />
        <Link
          to={generatePath(paths.tournaments, { leagueId })}
          className="inline-flex min-h-11 items-center text-body-md font-bold underline underline-offset-4"
        >
          {t("finals.common.backToTournaments")}
        </Link>
      </div>
      <p className="text-body-sm text-muted-foreground">
        {t("finals.finished.reopenNote")}
      </p>
    </div>
  );
}
