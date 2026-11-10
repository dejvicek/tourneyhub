import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link, Navigate, useNavigate } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  type BracketMatchData as BracketMatch,
  type BracketRoundData as BracketRound,
  type BracketSideData as BracketSide,
  finalsMutations,
  finalsQueries,
} from "@/features/finals/api";
import { leagueQueries } from "@/features/leagues/api";
import { useSeasonName } from "@/features/leagues/useSeasonName";
import { tournamentQueries } from "@/features/tournaments/api";
import { useLayout } from "@/hooks/useLayout";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import type { BracketContext } from "./finals/bracketContext";
import { BracketView, CompactBracket, RoundList } from "./finals/BracketView";
import { errorText } from "./finals/errorText";
import { resultPath } from "./finals/links";
import { useRoster } from "./finals/names";
import { PlacesSoFar } from "./finals/PlacesSoFar";
import { ScreenHeader } from "./finals/ScreenHeader";
import { LoadError, Loading } from "./finals/StateMessage";

/**
 * Screen 9: the knockout in progress (FR-037, BR-040–BR-045, BR-102). The
 * bracket for 4, 8 or 16 spots with byes, the third-place match, the final in
 * its own format, and the places already decided. Results are entered in the
 * result screens.
 */
export function KnockoutPage() {
  const { t } = useTranslation();
  const layout = useLayout();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const bracket = useQuery(finalsQueries.bracket(leagueId, tournamentId));
  const places = useQuery(finalsQueries.places(leagueId, tournamentId));
  const league = useQuery(leagueQueries.detail(leagueId));
  const seasons = useQuery(leagueQueries.seasons(leagueId));
  const seasonName = useSeasonName();
  const roster = useRoster(leagueId, tournament.data?.entries);
  const removal = useMutation(
    finalsMutations.deleteKnockout(queryClient, leagueId, tournamentId),
  );

  if (tournament.isError || bracket.isError) {
    return (
      <LoadError
        onRetry={() => {
          void tournament.refetch();
          void bracket.refetch();
        }}
      />
    );
  }
  const data = tournament.data;
  const shape = bracket.data;
  if (data === undefined || shape === undefined) {
    return <Loading />;
  }
  // FR-037: the last result finishes the tournament; its places are screen 10.
  if (data.state === "finished") {
    return (
      <Navigate
        to={generatePath(paths.finished, { leagueId, tournamentId })}
        replace
      />
    );
  }

  const format = data.phases.find((phase) => phase.kind === "group")?.format;
  const season = seasons.data?.find((s) => s.id === data.season_id);
  const ctx: BracketContext = {
    sideName: (side: BracketSide) =>
      side.is_bye
        ? t("finals.knockout.bye")
        : side.entry_id === null
          ? t("finals.knockout.tbd")
          : roster.entry(side.entry_id),
    resultHref: (match: BracketMatch) =>
      match.state === "ready" || match.state === "on_field"
        ? resultPath(leagueId, tournamentId, match.match_id, match.match_format)
        : null,
    matchTitle: (round: BracketRound, match: BracketMatch) =>
      match.kind === "third_place"
        ? t("finals.matchTitle.third_place")
        : t(`finals.matchTitle.${round.name}`, { n: match.position }),
  };
  const body =
    layout === "phone" ? (
      shape.size <= 4 ? (
        <CompactBracket bracket={shape} ctx={ctx} />
      ) : (
        <RoundList bracket={shape} ctx={ctx} />
      )
    ) : (
      <BracketView bracket={shape} ctx={ctx} />
    );
  const decided = (
    <PlacesSoFar
      rows={places.data?.rows ?? []}
      entryName={(entryId) => roster.entry(entryId)}
    />
  );

  return (
    <div className="space-y-6">
      <DocumentTitle screen={t("finals.knockout.title")} />
      <ScreenHeader
        kicker={
          league.data !== undefined && season !== undefined
            ? t("finals.common.kicker", {
                league: league.data.name,
                season: seasonName(season),
              })
            : undefined
        }
        title={data.name}
        subtitle={t("finals.knockout.title")}
      />
      {shape.has_group_phase && (
        <nav aria-label={t("finals.knockout.phases")}>
          <ul className="flex gap-1 rounded-lg bg-nav-active p-1">
            <li className="flex-1">
              <Link
                to={generatePath(
                  format === "round_robin"
                    ? paths.tournament
                    : paths.betweenRounds,
                  { leagueId, tournamentId },
                )}
                className="inline-flex h-11 w-full items-center justify-center rounded-md px-3 text-body-sm text-nav-active-foreground outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                {format === "round_robin"
                  ? t("finals.knockout.roundRobin")
                  : t("finals.rounds.title")}
              </Link>
            </li>
            <li className="flex-1">
              <Link
                to="."
                aria-current="page"
                className="inline-flex h-11 w-full items-center justify-center rounded-md bg-card px-3 text-body-sm font-bold text-card-foreground outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                {t("finals.knockout.knockout")}
              </Link>
            </li>
          </ul>
        </nav>
      )}
      {layout === "desktop" ? (
        <div className="grid grid-cols-[minmax(0,1fr)_18rem] gap-8">
          {body}
          <aside>{decided}</aside>
        </div>
      ) : (
        <>
          {body}
          {decided}
        </>
      )}
      {shape.has_group_phase && (
        <section className="space-y-2">
          {removal.isError && (
            <p role="alert" className="text-body-sm">
              {errorText(t, removal.error)}
            </p>
          )}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              {/* TODO(foundation-buttons) */}
              <Button type="button" variant="outline" className="min-h-11">
                {t("finals.knockout.delete")}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t("finals.knockout.deleteTitle")}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t("finals.knockout.deleteBody")}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>
                  {t("finals.common.cancel")}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => {
                    removal.mutate(shape.phase_id, {
                      onSuccess: () => {
                        void navigate(
                          generatePath(paths.tournament, {
                            leagueId,
                            tournamentId,
                          }),
                        );
                      },
                    });
                  }}
                >
                  {t("finals.knockout.deleteConfirm")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </section>
      )}
    </div>
  );
}
