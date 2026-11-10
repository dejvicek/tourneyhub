import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { finalsQueries } from "@/features/finals/api";
import { leagueQueries } from "@/features/leagues/api";
import { useSeasonName } from "@/features/leagues/useSeasonName";
import { tournamentQueries } from "@/features/tournaments/api";
import { localDate, shortName } from "@/features/tournaments/finals/names";
import { Notice } from "@/features/tournaments/finals/Notice";
import { LoadError, Loading } from "@/features/tournaments/finals/StateMessage";
import { usePlaceLabel } from "@/features/tournaments/finals/usePlaceLabel";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { standingsQueries } from "./api";

/**
 * The season's standings (FR-061, FR-022, BR-110–BR-113): every player who
 * has played in a finished tournament, with total placement points,
 * tournaments played and tournament wins. Built from the places table of
 * screen 10; the design has no board of its own.
 */
export function SeasonStandingsPage() {
  const { t, i18n } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const placeLabel = usePlaceLabel();
  const seasonName = useSeasonName();
  const seasons = useQuery(leagueQueries.seasons(leagueId));
  const [picked, setPicked] = useState<string | undefined>(undefined);
  const active = seasons.data?.find((s) => s.state === "active");
  const season =
    seasons.data?.find((s) => s.id === picked) ?? active ?? seasons.data?.[0];
  const standings = useQuery(standingsQueries.season(leagueId, season?.id));
  const players = useQuery(finalsQueries.players(leagueId));
  const tournaments = useQuery(
    tournamentQueries.ofSeason(leagueId, season?.id),
  );

  if (seasons.isError || standings.isError) {
    return (
      <LoadError
        onRetry={() => {
          void seasons.refetch();
          void standings.refetch();
        }}
      />
    );
  }
  if (season === undefined || standings.data === undefined) {
    return <Loading />;
  }

  const names = new Map(
    (players.data ?? []).map((p) => [p.id, shortName(p.name)] as const),
  );
  const finished = (tournaments.data ?? []).filter(
    (x) => x.state === "finished",
  );
  const table = season.placement_points;
  const list = new Intl.ListFormat(i18n.resolvedLanguage, {
    style: "short",
    type: "unit",
  });
  const number = new Intl.NumberFormat(i18n.resolvedLanguage);

  return (
    <div className="space-y-6">
      <DocumentTitle screen={t("standings.season.title")} />
      <header className="space-y-1">
        <h1 className="font-display text-display-screen md:text-display-title">
          {t("standings.season.title")}
        </h1>
        <p className="text-body-md text-muted-foreground">
          {t("standings.season.lead", {
            season: seasonName(season),
            count: finished.length,
          })}
        </p>
      </header>

      {(seasons.data?.length ?? 0) > 1 && (
        <div className="max-w-xs space-y-1">
          <label htmlFor="season-pick" className="text-caption font-bold">
            {t("standings.season.pick")}
          </label>
          <Select value={season.id} onValueChange={setPicked}>
            <SelectTrigger id="season-pick">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(seasons.data ?? []).map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {seasonName(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {standings.data.length === 0 ? (
        <Notice tone="info" title={t("standings.season.emptyTitle")}>
          {t("standings.season.emptyBody")}
        </Notice>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-72 border-collapse">
            <caption className="sr-only">{t("standings.season.title")}</caption>
            <thead>
              <tr className="text-caption text-muted-foreground">
                <th
                  scope="col"
                  className="w-12 py-2 pr-2 text-start font-normal"
                >
                  {t("standings.season.columns.place")}
                </th>
                <th scope="col" className="py-2 text-start font-normal">
                  {t("standings.season.columns.player")}
                </th>
                <th scope="col" className="w-14 py-2 text-end font-normal">
                  {t("standings.season.columns.played")}
                </th>
                <th scope="col" className="w-14 py-2 text-end font-normal">
                  {t("standings.season.columns.wins")}
                </th>
                <th scope="col" className="w-16 py-2 text-end font-normal">
                  {t("standings.season.columns.points")}
                </th>
              </tr>
            </thead>
            <tbody>
              {standings.data.map((row) => (
                <tr key={row.player_id} className="border-t border-border">
                  <td className="py-2.5 pr-2 font-display text-score-m">
                    {row.place}
                  </td>
                  <td className="py-2.5 text-body-md font-bold">
                    {names.get(row.player_id) ?? t("finals.common.unknown")}
                  </td>
                  <td className="py-2.5 text-end text-body-md">
                    {row.tournaments_played}
                  </td>
                  <td className="py-2.5 text-end text-body-md">
                    {row.tournament_wins}
                  </td>
                  <td className="py-2.5 text-end font-display text-score-l">
                    {number.format(row.points)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-caption text-muted-foreground">
        {t("standings.season.footnote", {
          last: placeLabel(table.length),
          points: list.format(table.map(String)),
        })}
      </p>

      {finished.length > 0 && (
        <section aria-labelledby="counted-heading" className="space-y-2">
          <h2
            id="counted-heading"
            className="font-display text-display-section"
          >
            {t("standings.season.counted")}
          </h2>
          <ul className="border-t border-border">
            {finished.map((x) => (
              <li key={x.id} className="border-b border-border">
                <Link
                  to={generatePath(paths.finished, {
                    leagueId,
                    tournamentId: x.id,
                  })}
                  className="flex min-h-11 items-center justify-between gap-3 py-2"
                >
                  <span className="text-body-md font-bold">{x.name}</span>
                  <span className="text-body-sm text-muted-foreground">
                    {t("finals.common.date", { date: localDate(x.date) })}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
