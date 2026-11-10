import { useMutation } from "@tanstack/react-query";
import { type CSSProperties, useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link, useNavigate } from "react-router";

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
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { setupMutations } from "@/features/tournaments/api";
import { paths } from "@/lib/paths";
import { cn } from "@/lib/utils";

import { shortDate } from "./dates";
import { MoreIcon } from "./icons";
import { entryName } from "./summary";

interface TournamentItemProps {
  leagueId: string;
  summary: components["schemas"]["TournamentSummary"];
  nameOf: (playerId: string) => string;
}

/** The design's Tournament item: status, title, date, detail and progress. */
export function TournamentItem({
  leagueId,
  summary,
  nameOf,
}: TournamentItemProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const remove = useMutation(setupMutations.remove(leagueId, summary.id));
  const backToSetup = useMutation(
    setupMutations.backToSetup(leagueId, summary.id),
  );
  const progress = summary.progress;
  const canGoBack =
    summary.state === "in_progress" && progress?.matches_played === 0;

  const detailText = (() => {
    if (summary.state === "setup") {
      return t("tournaments.list.picked", { count: summary.player_count });
    }
    if (summary.state === "finished") {
      const winner = summary.winner_player_ids;
      return [
        winner === null || winner.length === 0
          ? ""
          : t("tournaments.list.wonBy", {
              names: entryName(t, winner.map(nameOf)),
            }),
        t("tournaments.list.players", { count: summary.player_count }),
      ]
        .filter((text) => text !== "")
        .join(" ");
    }
    if (progress === null) {
      return "";
    }
    const group = summary.phases.find((phase) => phase.kind === "group");
    const phase = progress.in_knockout
      ? t("tournaments.list.phase.knockout")
      : group?.format === "round_robin"
        ? t("tournaments.list.phase.roundRobin", {
            round: progress.round_no,
            rounds: progress.round_count,
          })
        : group?.format === "swiss"
          ? t("tournaments.list.phase.swiss", { round: progress.round_no })
          : group?.format === "monster_dyp"
            ? t("tournaments.list.phase.monsterDyp", {
                round: progress.round_no,
              })
            : t("tournaments.list.phase.knockout");
    return `${phase} ${t("tournaments.list.played", {
      played: progress.matches_played,
      count: progress.match_count,
    })}`;
  })();

  const percent =
    progress === null || progress.match_count === 0
      ? 0
      : Math.round((progress.matches_played / progress.match_count) * 100);

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
        <span className="text-body-sm text-muted-foreground">{detailText}</span>
        {summary.state === "in_progress" && progress !== null && (
          <span
            role="progressbar"
            aria-label={t("tournaments.list.progress", { name: summary.name })}
            aria-valuemin={0}
            aria-valuemax={progress.match_count}
            aria-valuenow={progress.matches_played}
            className="mt-1 block h-2 overflow-hidden rounded-full bg-nav-active"
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
