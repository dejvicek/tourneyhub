import { useMutation, useQuery } from "@tanstack/react-query";
import { cn } from "cn";
import { type CSSProperties, useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link, useNavigate } from "react-router";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { TournamentSummary } from "@/demo/contract";
import {
  setupMutations,
  setupQueries,
  type TournamentDetail,
} from "@/features/tournaments/api";
import { paths } from "@/lib/paths";

import { shortDate } from "./dates";
import { MoreIcon } from "./icons";
import { entryName, typeLabel } from "./summary";

interface TournamentItemProps {
  leagueId: string;
  summary: TournamentSummary;
  /** Absent while the tournament's details are loading. */
  detail: TournamentDetail | undefined;
  nameOf: (playerId: string) => string;
}

/** The first phase's rounds and how many matches were played so far. */
function progressOf(detail: TournamentDetail) {
  const matches = detail.rounds.flatMap((round) => round.matches);
  const group = detail.phases.find((phase) => phase.kind === "group");
  const knockout = detail.phases.find((phase) => phase.kind === "knockout");
  const groupRounds = detail.rounds.filter(
    (round) => round.phase_id === group?.id,
  );
  const inKnockout =
    knockout !== undefined &&
    detail.rounds.some((round) => round.phase_id === knockout.id);
  const current =
    groupRounds.find((round) =>
      round.matches.some((match) => match.outcome === null),
    ) ?? groupRounds.at(-1);
  return {
    played: matches.filter((match) => match.outcome !== null).length,
    total: matches.length,
    group,
    inKnockout,
    round: current?.round_no ?? 1,
    rounds: groupRounds.length,
  };
}

/** The design's Tournament item: status, title, date, detail and progress. */
export function TournamentItem({
  leagueId,
  summary,
  detail,
  nameOf,
}: TournamentItemProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const remove = useMutation(setupMutations.remove(leagueId, summary.id));
  const backToSetup = useMutation(
    setupMutations.backToSetup(leagueId, summary.id),
  );
  const setup = useQuery(
    setupQueries.detail(
      leagueId,
      summary.state === "setup" ? summary.id : undefined,
    ),
  );

  const loaded =
    detail === undefined ? undefined : { detail, progress: progressOf(detail) };
  const progress = loaded?.progress;
  const canGoBack = summary.state === "in_progress" && progress?.played === 0;

  const detailText = (() => {
    if (summary.state === "setup") {
      return setup.data === undefined
        ? ""
        : t("tournaments.list.picked", { count: setup.data.player_ids.length });
    }
    if (loaded === undefined) {
      return "";
    }
    const { detail: read, progress: made } = loaded;
    if (summary.state === "finished") {
      const winner = read.places?.find((row) => row.place === 1);
      const entry = read.entries.find((e) => e.id === winner?.entry_id);
      const players = read.entries
        .filter((e) => e.stage === "main")
        .flatMap((e) => e.player_ids).length;
      return [
        entry === undefined
          ? ""
          : t("tournaments.list.wonBy", {
              names: entryName(t, entry.player_ids.map(nameOf)),
            }),
        t("tournaments.list.players", { count: players }),
      ]
        .filter((text) => text !== "")
        .join(" ");
    }
    const phase = made.inKnockout
      ? t("tournaments.list.phase.knockout")
      : made.group?.format === "round_robin"
        ? t("tournaments.list.phase.roundRobin", {
            round: made.round,
            rounds: made.rounds,
          })
        : made.group?.format === "swiss"
          ? t("tournaments.list.phase.swiss", { round: made.round })
          : made.group?.format === "monster_dyp"
            ? t("tournaments.list.phase.monsterDyp", { round: made.round })
            : t("tournaments.list.phase.knockout");
    return `${phase} ${t("tournaments.list.played", {
      played: made.played,
      count: made.total,
    })}`;
  })();

  const percent =
    progress === undefined || progress.total === 0
      ? 0
      : Math.round((progress.played / progress.total) * 100);

  return (
    <li
      className={cn(
        "flex items-start rounded-lg border border-border-surface bg-card",
        summary.state === "in_progress" && "border-team-a",
      )}
    >
      <Link
        to={generatePath(paths.tournament, {
          leagueId,
          tournamentId: summary.id,
        })}
        className="grid min-h-11 flex-1 gap-1.5 rounded-lg p-4 outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <span className="flex items-center gap-2 text-body-sm font-bold">
          <span
            aria-hidden="true"
            className={cn(
              "size-3 shrink-0 rounded-full border-2",
              summary.state === "in_progress" && "border-team-a bg-team-a",
              summary.state === "setup" && "border-foreground",
              summary.state === "finished" && "border-foreground bg-foreground",
            )}
          />
          {t(`tournaments.list.status.${summary.state}`)}
        </span>
        <span className="flex items-baseline justify-between gap-3">
          <span className="font-display text-display-name break-words">
            {summary.name}
          </span>
          <span className="shrink-0 text-caption text-muted-foreground">
            {shortDate(summary.date)}
          </span>
        </span>
        <span className="text-body-sm text-muted-foreground">
          {typeLabel(t, summary.type)}
          {detailText === "" ? "" : `. ${detailText}`}
        </span>
        {summary.state === "in_progress" && progress !== undefined && (
          <span
            role="progressbar"
            aria-label={t("tournaments.list.progress", { name: summary.name })}
            aria-valuemin={0}
            aria-valuemax={progress.total}
            aria-valuenow={progress.played}
            className="mt-1 block h-2 overflow-hidden rounded-full bg-muted"
          >
            {/* A value from the API reaches CSS through a custom property (§5.1). */}
            <span
              style={{ "--progress": `${String(percent)}%` } as CSSProperties}
              className="block h-full w-(--progress) bg-primary"
            />
          </span>
        )}
      </Link>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="m-1"
            aria-label={t("tournaments.list.actions", { name: summary.name })}
          >
            <MoreIcon />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {canGoBack && (
            <DropdownMenuItem
              className="min-h-11"
              onSelect={() => {
                backToSetup.mutate("in_progress", {
                  onSuccess: () => {
                    void navigate(
                      generatePath(paths.setupReview, {
                        leagueId,
                        tournamentId: summary.id,
                      }),
                    );
                  },
                });
              }}
            >
              {t("tournaments.list.backToSetup")}
            </DropdownMenuItem>
          )}
          <DropdownMenuItem
            variant="destructive"
            className="min-h-11"
            onSelect={() => {
              setConfirmingDelete(true);
            }}
          >
            {t("tournaments.list.delete")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <AlertDialog open={confirmingDelete} onOpenChange={setConfirmingDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("tournaments.list.deleteTitle", { name: summary.name })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("tournaments.list.deleteBody")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("tournaments.list.keep")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                remove.mutate();
              }}
            >
              {t("tournaments.list.deleteConfirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  );
}
