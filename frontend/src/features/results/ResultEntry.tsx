import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ApiError, ErrorCode } from "@/api/client";
import type { components } from "@/api/schema";
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
import { finalsQueries } from "@/features/finals/api";
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

type PlayRead = components["schemas"]["PlayRead"];

interface ResultEntryProps {
  leagueId: string;
  model: PlayModel;
  play: PlayRead | undefined;
  matchId: string;
  onDone: () => void;
}

/** The codes of a result with a text of their own (ADR-008). */
const CODE_TEXTS = {
  season_closed: "results.errors.seasonClosed",
  draws_not_allowed: "results.errors.draw",
  scores_required: "results.errors.scores",
  game_score_mismatch: "results.errors.mismatch",
  result_does_not_fit_format: "results.errors.format",
  match_sides_unknown: "results.unknownSides",
  group_phase_locked: "results.errors.locked",
  result_locked: "results.errors.lockedKnockout",
  match_sides_changed: "results.errors.sidesChanged",
} as const satisfies Partial<Record<ErrorCode, string>>;

function hasText(code: ErrorCode | undefined): code is keyof typeof CODE_TEXTS {
  return code !== undefined && code in CODE_TEXTS;
}

function useResultError(error: ApiError | null): string | null {
  const { t } = useTranslation();
  if (error === null) {
    return null;
  }
  if (hasText(error.code)) {
    return t(CODE_TEXTS[error.code], { game: Number(error.detail.game_no) });
  }
  return error.status === 404 || error.status === 409
    ? t("results.errors.changed")
    : t("results.errors.generic");
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
  const league = useQuery(leagueQueries.detail(leagueId));
  const save = useMutation(
    resultMutations.save(leagueId, model.tournament.id, matchId),
  );
  const errorText = useResultError(save.error);
  const info = model.matches.get(matchId);
  // A knockout match's bracket gives its seeds and whether a later match
  // locks it (BR-094); the group phase needs neither.
  const inKnockout = info?.phase.kind === "knockout";
  const bracket = useQuery({
    ...finalsQueries.bracket(leagueId, model.tournament.id),
    enabled: inKnockout,
  });
  const bracketMatch = bracket.data?.rounds
    .flatMap((round) => round.matches)
    .find((m) => m.match_id === matchId);
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
  // BR-053: the round robin's results lock once the knockout is drawn;
  // BR-094: a knockout result locks once a later match has one.
  const lock =
    phase.kind === "group" && model.knockout !== undefined
      ? "group"
      : bracketMatch?.result_locked === true
        ? "knockout"
        : null;
  const locked = lock !== null;
  // ADR-008: a result names the entries the screen saw on both sides, so a
  // later match whose sides have changed since is refused, not decided for
  // someone else (BR-094).
  const [seenA, seenB] = [sideA.entry_id, sideB.entry_id];
  const expectedSides: [string, string] | null =
    seenA !== null && seenB !== null ? [seenA, seenB] : null;
  const onSave: ResultFormContext["onSave"] = (body) => {
    save.mutate(
      { ...body, expected_sides: expectedSides },
      { onSuccess: onDone },
    );
  };
  // The bracket's seeds, as the bracket shows them (BR-042), not the setup's.
  const seedOf = (entryId: string | null, index: 0 | 1) =>
    bracketMatch !== undefined
      ? (bracketMatch.sides[index]?.seed ?? null)
      : entryId === null || inKnockout
        ? null
        : (model.entries.get(entryId)?.seed ?? null);
  const actions = (
    <>
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
    </>
  );
  const context: ResultFormContext = {
    info,
    names: [names.side(sideA), names.side(sideB)],
    firstNames: [names.sideFirst(sideA), names.sideFirst(sideB)],
    seeds: [seedOf(sideA.entry_id, 0), seedOf(sideB.entry_id, 1)],
    goalsPerGame: model.tournament.goals_per_game,
    required: scoresRequired(phase),
    drawAllowed: drawsAllowed(phase, league.data?.draws_allowed ?? false),
    locked,
    pending: save.isPending,
    standings: play?.standings,
    onSave,
    actions,
  };

  return (
    <div className="space-y-4">
      {lock !== null && (
        <Notice variant="warning" title={t(`results.locked.${lock}.title`)}>
          {t(`results.locked.${lock}.body`)}
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
        >
          {actions}
        </WalkoverForm>
      ) : info.format === "bo1" ? (
        <SimpleResultForm context={context} />
      ) : (
        <BestOfResultPage context={context} />
      )}
    </div>
  );
}
