import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ApiError } from "@/api/client";
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
import type { PlayRead } from "@/demo/contract";
import { leagueQueries } from "@/features/leagues/api";
import { resultMutations } from "@/features/results/api";
import { type PlayModel, sidesOf } from "@/features/tournaments/play/model";
import { Notice } from "@/features/tournaments/play/Notice";
import { useNames } from "@/features/tournaments/play/useNames";

import { BestOfResultPage } from "./BestOfResultPage";
import type { ResultFormContext } from "./formContext";
import { drawsAllowed, scoresRequired } from "./resultDraft";
import { SimpleResultForm } from "./SimpleResultForm";
import { WalkoverForm } from "./WalkoverForm";

interface ResultEntryProps {
  leagueId: string;
  model: PlayModel;
  play: PlayRead | undefined;
  matchId: string;
  onDone: () => void;
}

function useResultError(error: ApiError | null): string | null {
  const { t } = useTranslation();
  if (error === null) {
    return null;
  }
  switch (error.detail.reason) {
    case "draw_not_allowed":
      return t("results.errors.draw");
    case "scores_required":
    case "one_score":
      return t("results.errors.scores");
    case "results_locked":
      return t("results.errors.locked");
    default:
      return error.status === 404 || error.status === 409
        ? t("results.errors.changed")
        : t("results.errors.generic");
  }
}

/**
 * The result of one match (screens 7 and 7b): the BO1 form or the best-of
 * form by the match's format, the walkover and clearing (FR-050–FR-053).
 */
export function ResultEntry({
  leagueId,
  model,
  play,
  matchId,
  onDone,
}: ResultEntryProps) {
  const { t } = useTranslation();
  const names = useNames(model);
  const settings = useQuery(leagueQueries.settings(leagueId));
  const save = useMutation(
    resultMutations.save(leagueId, model.tournament.id, matchId),
  );
  const errorText = useResultError(save.error);
  const info = model.matches.get(matchId);
  const [walkover, setWalkover] = useState(info?.match.is_walkover ?? false);

  if (!info) {
    return <p role="alert">{t("results.errors.changed")}</p>;
  }
  const { match, phase } = info;
  const [sideA, sideB] = sidesOf(match);
  const known = match.sides.every((side) => side.player_ids.length > 0);
  if (!known) {
    return <p>{t("results.unknownSides")}</p>;
  }
  // BR-053: the round robin's results lock once the knockout is drawn.
  const locked = phase.kind === "group" && model.knockout !== undefined;
  const onSave: ResultFormContext["onSave"] = (body) => {
    save.mutate(body, { onSuccess: onDone });
  };
  const seedOf = (entryId: string | null) =>
    entryId === null ? null : (model.entries.get(entryId)?.seed ?? null);
  const context: ResultFormContext = {
    info,
    names: [names.side(sideA), names.side(sideB)],
    firstNames: [names.sideFirst(sideA), names.sideFirst(sideB)],
    seeds: [seedOf(sideA.entry_id), seedOf(sideB.entry_id)],
    goalsPerGame: model.tournament.goals_per_game,
    required: scoresRequired(phase),
    drawAllowed: drawsAllowed(phase, settings.data?.draws_allowed ?? false),
    locked,
    pending: save.isPending,
    standings: play?.standings,
    onSave,
  };

  return (
    <div className="space-y-4">
      {locked && (
        <Notice variant="warning" title={t("results.locked.title")}>
          {t("results.locked.body")}
        </Notice>
      )}
      {walkover ? (
        <WalkoverForm
          names={context.names}
          initial={
            match.is_walkover
              ? match.outcome === "side_2"
                ? "side_2"
                : "side_1"
              : null
          }
          pending={save.isPending || locked}
          onSave={onSave}
          onCancel={() => {
            setWalkover(false);
          }}
        />
      ) : info.format === "bo1" ? (
        <SimpleResultForm context={context} />
      ) : (
        <BestOfResultPage context={context} />
      )}
      {errorText !== null && (
        <p role="alert" className="text-body-md font-bold text-destructive">
          {errorText}
        </p>
      )}
      {!walkover && !locked && (
        <Button
          type="button"
          variant="text"
          className="w-full"
          onClick={() => {
            setWalkover(true);
          }}
        >
          {t("results.walkover.open")}
        </Button>
      )}
      {match.outcome !== null && !locked && (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              type="button"
              variant="text"
              className="w-full text-destructive"
            >
              {t("results.clear.open")}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t("results.clear.title")}</AlertDialogTitle>
              <AlertDialogDescription>
                {t(
                  model.tournament.state === "finished"
                    ? "results.clear.bodyFinished"
                    : "results.clear.body",
                  { match: names.match(match.sides) },
                )}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t("results.clear.cancel")}</AlertDialogCancel>
              <AlertDialogAction
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                onClick={() => {
                  onSave({ walkover_winner: null, games: [] });
                }}
              >
                {t("results.clear.confirm")}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  );
}
