import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link, Outlet, useNavigate } from "react-router";

import { ApiError } from "@/api/client";
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
  type BracketSideData as BracketSide,
  finalsMutations,
  finalsQueries,
} from "@/features/finals/api";
import { tournamentQueries } from "@/features/tournaments/api";
import { useLayout } from "@/hooks/useLayout";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { type BracketContext, bracketTitles } from "./finals/bracketContext";
import { BracketView, CompactBracket, RoundList } from "./finals/BracketView";
import { errorText } from "./finals/errorText";
import { FinalFormat } from "./finals/FinalFormat";
import { resultPath } from "./finals/links";
import { useRoster } from "./finals/names";
import { Notice } from "./finals/Notice";
import { PlacesSoFar } from "./finals/PlacesSoFar";
import { ScreenHeader } from "./finals/ScreenHeader";
import { LoadError, Loading } from "./finals/StateMessage";

/**
 * Screen 9: the knockout in progress (FR-037, BR-040–BR-045, BR-102). The
 * bracket for 4, 8 or 16 spots with byes, the third-place match, the final in
 * its own format, which can change while the final has no result (FR-054),
 * and the places already decided. Results are entered in the result screens.
 */
export function KnockoutPage() {
  const { t } = useTranslation();
  return (
    <div className="space-y-6">
      <DocumentTitle screen={t("finals.knockout.title")} />
      <ScreenHeader title={t("finals.knockout.title")} />
      <KnockoutContent />
      <Outlet />
    </div>
  );
}

function KnockoutContent() {
  const { t } = useTranslation();
  const layout = useLayout();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const bracket = useQuery(finalsQueries.bracket(leagueId, tournamentId));
  const places = useQuery(finalsQueries.places(leagueId, tournamentId));
  const roster = useRoster(leagueId, tournament.data?.entries);
  const removal = useMutation(
    finalsMutations.deleteKnockout(queryClient, leagueId, tournamentId),
  );

  // A tournament without a knockout has no bracket (404).
  if (bracket.error instanceof ApiError && bracket.error.status === 404) {
    return <Notice tone="info" title={t("finals.knockout.noKnockout")} />;
  }
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

  const ctx: BracketContext = {
    sideName: (side: BracketSide) =>
      side.is_bye
        ? t("finals.knockout.bye")
        : side.entry_id === null
          ? t("finals.knockout.tbd")
          : roster.entry(side.entry_id),
    canChange: true,
    resultHref: (match: BracketMatch) =>
      match.state === "ready" ||
      match.state === "on_field" ||
      (match.state === "played" && !match.result_locked)
        ? resultPath("knockout", leagueId, tournamentId, match.match_id)
        : null,
    ...bracketTitles(t, shape),
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
      {data.state === "finished" && (
        // FR-037: the last result finishes the tournament; its places are screen 10.
        <Notice tone="info" title={t("finals.knockout.finishedTitle")}>
          <Link
            to={generatePath(paths.finished, { leagueId, tournamentId })}
            className="inline-flex min-h-11 items-center font-bold underline underline-offset-4"
          >
            {t("finals.knockout.seePlaces")}
          </Link>
        </Notice>
      )}
      {layout === "desktop" && shape.size <= 4 ? (
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
      <FinalFormat
        leagueId={leagueId}
        tournamentId={tournamentId}
        bracket={shape}
      />
      {shape.has_group_phase && (
        <section className="space-y-2">
          {removal.isError && (
            <p role="alert" className="text-body-sm">
              {errorText(t, removal.error)}
            </p>
          )}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button type="button" variant="outline">
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
