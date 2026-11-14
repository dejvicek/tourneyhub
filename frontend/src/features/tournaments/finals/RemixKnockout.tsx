import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link, useNavigate } from "react-router";

import { ApiError } from "@/api/client";
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
import { finalsMutations, finalsQueries } from "@/features/finals/api";
import type { TournamentDetail } from "@/features/tournaments/api";
import { paths } from "@/lib/paths";

import { errorText } from "./errorText";
import { FinalFormat } from "./FinalFormat";
import { resultPath } from "./links";
import type { Roster } from "./names";
import { Notice } from "./Notice";
import { PlacesSoFar } from "./PlacesSoFar";
import { nextRoundName } from "./remix";
import type { RemixMatch } from "./RemixMatchCard";
import { RemixRounds } from "./RemixRounds";
import { LoadError, Loading } from "./StateMessage";

interface RemixKnockoutProps {
  leagueId: string;
  tournamentId: string;
  tournament: TournamentDetail;
  roster: Roster;
}

/**
 * Screen 9 for a Lord have mercy knockout (BR-155): the rounds drawn so far,
 * the draw of the next round once the round before is complete (BR-140), the
 * places so far, the final's format and the deletion of the newest round
 * (FR-046, BR-146). It never asks for the bracket, which this mode has none of.
 */
export function RemixKnockout({
  leagueId,
  tournamentId,
  tournament,
  roster,
}: RemixKnockoutProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const knockout = useQuery(
    finalsQueries.knockoutRounds(leagueId, tournamentId),
  );
  const places = useQuery(finalsQueries.places(leagueId, tournamentId));
  const draw = useMutation(
    finalsMutations.drawKnockoutRound(queryClient, leagueId, tournamentId),
  );
  const removal = useMutation(
    finalsMutations.deleteKnockoutRound(queryClient, leagueId, tournamentId),
  );

  // Deleting round 1 deletes the knockout, so a reload then finds none (404).
  if (knockout.error instanceof ApiError && knockout.error.status === 404) {
    return <Notice tone="info" title={t("finals.knockout.noKnockout")} />;
  }
  if (knockout.isError) {
    return (
      <LoadError
        onRetry={() => {
          void knockout.refetch();
        }}
      />
    );
  }
  const data = knockout.data;
  if (data === undefined) {
    return <Loading />;
  }

  const newest = data.rounds.at(-1);
  const upNext = nextRoundName(data);
  // The names read in a sentence: "Draw the semifinals".
  const roundName = (name: NonNullable<typeof upNext>) =>
    t(`finals.roundName.${name}`);
  const inSentence = (name: NonNullable<typeof upNext>) =>
    roundName(name).toLocaleLowerCase(i18n.resolvedLanguage);
  const open =
    newest?.matches.filter(
      (match) => match.state === "ready" || match.state === "on_field",
    ).length ?? 0;
  const final = data.rounds.length === data.round_count ? newest : undefined;
  const finalMatch = final?.matches.find((match) => match.kind === "standard");
  const list = new Intl.ListFormat(i18n.resolvedLanguage, {
    style: "short",
    type: "unit",
  });

  const deleteLabel =
    newest === undefined
      ? null
      : t("finals.remix.deleteRound", { round: inSentence(newest.name) });
  // BR-087: round 1 takes the knockout with it; a count of 0 reads without a number.
  const deleteBody =
    newest === undefined
      ? null
      : newest.round_no === 1
        ? newest.result_count === 0
          ? t("finals.remix.deleteBodyFirstNone")
          : t("finals.remix.deleteBodyFirst", { count: newest.result_count })
        : newest.result_count === 0
          ? t("finals.remix.deleteBodyNone")
          : t("finals.remix.deleteBody", { count: newest.result_count });

  const resultHref = (match: RemixMatch): string | null =>
    match.state === "bye"
      ? null
      : resultPath("knockout", leagueId, tournamentId, match.match_id);

  return (
    <div className="space-y-6">
      {tournament.state === "finished" && (
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
      {data.left_player_ids.length > 0 && (
        // FR-049, BR-149: a player who left stays in the draw.
        <Notice
          tone="info"
          title={t("finals.remix.leftNotice", {
            count: data.left_player_ids.length,
            names: list.format(data.left_player_ids.map(roster.player)),
          })}
        />
      )}
      {data.can_draw_next && newest !== undefined && upNext !== null && (
        <Notice
          tone="info"
          title={t("finals.remix.betweenTitle", {
            round: roundName(newest.name),
          })}
          className="space-y-3"
        >
          <Button
            type="button"
            size="lg"
            className="w-full md:w-auto"
            disabled={draw.isPending}
            onClick={() => {
              // ADR-008: the draw expects the round number it is looking at.
              draw.mutate({ expected_round_no: data.rounds.length + 1 });
            }}
          >
            {t("finals.remix.drawNext", { name: inSentence(upNext) })}
          </Button>
        </Notice>
      )}
      {!data.can_draw_next &&
        newest !== undefined &&
        tournament.state === "in_progress" &&
        open > 0 && (
          <Notice
            tone="info"
            title={t("finals.remix.inProgressTitle", {
              round: inSentence(newest.name),
            })}
          >
            {t("finals.remix.inProgressBody", { count: open })}
          </Notice>
        )}
      {draw.isError && (
        <p role="alert" className="text-body-sm">
          {errorText(t, draw.error)}
        </p>
      )}
      <RemixRounds
        knockout={data}
        ctx={{ playerName: roster.player, resultHref }}
      />
      <PlacesSoFar
        rows={places.data?.rows ?? []}
        entryName={(entryId) => roster.entry(entryId)}
      />
      <FinalFormat
        leagueId={leagueId}
        tournamentId={tournamentId}
        finalMatchFormat={data.final_match_format}
        finalHasResult={finalMatch !== undefined && finalMatch.outcome !== null}
      />
      {newest !== undefined && (
        <section className="space-y-2">
          {removal.isError && (
            <p role="alert" className="text-body-sm">
              {errorText(t, removal.error)}
            </p>
          )}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button type="button" variant="outline">
                {deleteLabel}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t("finals.remix.deleteTitle", {
                    round: inSentence(newest.name),
                  })}
                </AlertDialogTitle>
                <AlertDialogDescription>{deleteBody}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>
                  {t("finals.common.cancel")}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => {
                    // The reload after the delete can swap this component for
                    // the "no knockout" view before a per-call onSuccess runs,
                    // so the navigation hangs on the promise (errors show via
                    // removal.isError).
                    removal
                      .mutateAsync(newest.round_id)
                      .then(() => {
                        // BR-087: deleting round 1 deleted the knockout.
                        if (newest.round_no === 1) {
                          void navigate(
                            generatePath(paths.tournament, {
                              leagueId,
                              tournamentId,
                            }),
                          );
                        }
                      })
                      .catch(() => undefined);
                  }}
                >
                  {deleteLabel}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </section>
      )}
    </div>
  );
}
