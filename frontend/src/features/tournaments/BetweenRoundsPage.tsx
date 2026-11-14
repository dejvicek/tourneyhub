import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link, Outlet, useNavigate } from "react-router";

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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { playQueries } from "@/features/fields/api";
import {
  finalsMutations,
  finalsQueries,
  type TournamentData,
} from "@/features/finals/api";
import { resultMutations } from "@/features/results/api";
import { tournamentQueries } from "@/features/tournaments/api";
import { useLayout } from "@/hooks/useLayout";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";
import { cn } from "@/lib/utils";

type MatchData = TournamentData["rounds"][number]["matches"][number];
import { errorText, finishErrorText } from "./finals/errorText";
import { resultPath } from "./finals/links";
import { localDate, useRoster } from "./finals/names";
import { Notice } from "./finals/Notice";
import { qualifiersOf } from "./finals/qualifiers";
import { RankingTable } from "./finals/RankingTable";
import { scoreOf } from "./finals/score";
import { ScreenHeader } from "./finals/ScreenHeader";
import { LoadError, Loading } from "./finals/StateMessage";
import { TiebreakerSheet } from "./finals/TiebreakerSheet";
import { useEntryCount } from "./play/useEntryNoun";

/** BR-068: log2 of the entries, rounded up (the demo's engine has the same rule). */
function recommendedRounds(count: number): number {
  return Math.max(1, Math.ceil(Math.log2(Math.max(count, 1))));
}

/**
 * Screen 11: a Swiss or Monster DYP between rounds (FR-040–FR-046, FR-043,
 * BR-064–BR-068, BR-072, BR-073). Results of a round, who sat out or is
 * disabled, the decision to add a round, start the knockout or finish, and
 * the standings with BH1 and BH2.
 */
export function BetweenRoundsPage() {
  const { t } = useTranslation();
  return (
    <div className="space-y-6">
      <DocumentTitle screen={t("finals.rounds.title")} />
      <ScreenHeader title={t("finals.rounds.title")} />
      <RoundsContent />
      <Outlet />
    </div>
  );
}

function RoundsContent() {
  const { t, i18n } = useTranslation();
  const entryCount = useEntryCount();
  const layout = useLayout();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  // FR-043: the standings with BH1 and BH2, computed on read (ADR-009).
  const play = useQuery(playQueries.view(leagueId, tournamentId));
  const participants = useQuery(
    finalsQueries.participants(leagueId, tournamentId),
  );
  const roster = useRoster(leagueId, tournament.data?.entries);
  const addRound = useMutation(
    finalsMutations.addRound(queryClient, leagueId, tournamentId),
  );
  const removeRound = useMutation(
    finalsMutations.deleteRound(queryClient, leagueId, tournamentId),
  );
  const finish = useMutation(resultMutations.finish(leagueId, tournamentId));
  const [picked, setPicked] = useState<number | undefined>(undefined);

  if (tournament.isError || play.isError) {
    return (
      <LoadError
        onRetry={() => {
          void tournament.refetch();
          void play.refetch();
        }}
      />
    );
  }
  const data = tournament.data;
  const standings = play.data;
  if (data === undefined || standings === undefined) {
    return <Loading />;
  }

  const group = data.phases.find((phase) => phase.kind === "group");
  // Only Swiss and Monster DYP play rounds one by one (FR-040).
  if (group?.format !== "swiss" && group?.format !== "monster_dyp") {
    return <Notice tone="info" title={t("finals.rounds.notRounds")} />;
  }
  const rounds = data.rounds
    .filter((round) => round.phase_id === group.id)
    .sort((a, b) => a.round_no - b.round_no);
  const latest = rounds.at(-1);
  const current = rounds.find((r) => r.round_no === picked) ?? latest;
  const format = group.match_format;
  const hasKnockout = data.phases.some((phase) => phase.kind === "knockout");
  // Every match of the group phase has a result (FR-040).
  const complete = standings.group_done;
  const mainEntries = data.entries.filter((e) => e.stage === "main");
  const disabled = new Set(
    mainEntries.filter((e) => e.is_disabled).map((e) => e.id),
  );
  // BR-072: the organizer's tie-breakers in their order; none is null.
  const tiebreakers = group.tiebreakers ?? [];
  const qualifiers = qualifiersOf(data.phases);
  const active = mainEntries.filter((e) => !e.is_disabled).length;
  const open = latest?.matches.filter((m) => m.outcome === null).length ?? 0;
  const disabledNames = (participants.data ?? [])
    .filter(
      (p) =>
        p.state === "disabled" &&
        (p.disabled_since_round ?? 0) <= (current?.round_no ?? 0),
    )
    .map((p) => roster.entry(p.entry_id));
  const list = new Intl.ListFormat(i18n.resolvedLanguage, {
    style: "short",
    type: "unit",
  });
  const mutationError = addRound.error ?? removeRound.error;

  const matchRow = (match: MatchData) => {
    const score = scoreOf(match, format);
    const [one, two] = match.sides;
    if (one === undefined || two === undefined) {
      return null;
    }
    const winner = match.outcome;
    const title = `${roster.team(one.player_ids)} ${t("finals.start.versusLong")} ${roster.team(two.player_ids)}`;
    return (
      <li
        key={match.id}
        className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-x-3 border-b border-border py-2.5"
      >
        <span
          className={cn(
            "text-body-md break-words",
            winner === "side_1" && "font-bold",
          )}
        >
          {roster.team(one.player_ids)}
        </span>
        {score === null ? (
          <Button asChild>
            <Link
              to={resultPath("rounds", leagueId, tournamentId, match.id)}
              aria-label={t("finals.rounds.noResultFor", { match: title })}
            >
              {t("finals.rounds.noResult")}
            </Link>
          </Button>
        ) : (
          <span className="font-display text-score-m whitespace-nowrap">
            {score[0]} : {score[1]}
          </span>
        )}
        <span
          className={cn(
            "text-end text-body-md break-words",
            winner === "side_2" && "font-bold",
          )}
        >
          {roster.team(two.player_ids)}
        </span>
      </li>
    );
  };

  const roundsSection = (
    <section aria-labelledby="rounds-heading" className="space-y-4">
      <h2 id="rounds-heading" className="sr-only">
        {t("finals.rounds.title")}
      </h2>
      <ToggleGroup
        type="single"
        aria-label={t("finals.rounds.roundChips")}
        value={String(current?.round_no)}
        onValueChange={(value) => {
          if (value !== "") {
            setPicked(Number(value));
          }
        }}
      >
        {rounds.map((round) => (
          <ToggleGroupItem key={round.id} value={String(round.round_no)}>
            {t("finals.rounds.chip", { round: round.round_no })}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {current === undefined || current.matches.length === 0 ? (
        <p className="text-body-sm text-muted-foreground">
          {t("finals.rounds.noMatches")}
        </p>
      ) : (
        <ul
          aria-label={t("finals.rounds.matches", { round: current.round_no })}
          className="border-t border-border"
        >
          {current.matches.map(matchRow)}
        </ul>
      )}
      {current !== undefined && current.sitting_out.length > 0 && (
        <p className="text-body-sm">
          {t("finals.rounds.satOut", {
            names: list.format(
              current.sitting_out.map((id) => roster.entry(id)),
            ),
          })}
        </p>
      )}
      {disabledNames.length > 0 && (
        <p className="text-body-sm">
          {t("finals.rounds.disabled", { names: list.format(disabledNames) })}
        </p>
      )}
      {mutationError !== null && (
        <p role="alert" className="text-body-sm">
          {errorText(t, mutationError)}
        </p>
      )}
      {finish.isError && (
        <p role="alert" className="text-body-sm">
          {finishErrorText(t, finish.error)}
        </p>
      )}
      {latest !== undefined && !hasKnockout && complete && (
        <section
          aria-labelledby="decision-heading"
          className="space-y-3 rounded-lg border-2 border-team-a bg-card p-4 text-card-foreground"
        >
          <h3 id="decision-heading" className="text-body-lg font-bold">
            {t("finals.rounds.decisionTitle", { round: latest.round_no })}
          </h3>
          <p className="text-body-md">
            {t("finals.rounds.decisionBody", {
              count: recommendedRounds(active),
              active,
              played: rounds.length,
            })}
          </p>
          <div className="flex flex-col gap-2">
            <Button
              type="button"
              size="lg"
              disabled={addRound.isPending}
              onClick={() => {
                addRound.mutate({ expected_round_no: rounds.length + 1 });
              }}
            >
              {t("finals.rounds.addRound", { round: rounds.length + 1 })}
            </Button>
            <Button asChild variant="secondary">
              <Link
                to={generatePath(paths.startKnockout, {
                  leagueId,
                  tournamentId,
                })}
              >
                {t("finals.rounds.startKnockout")}
              </Link>
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button type="button" variant="text">
                  {t("finals.rounds.finish")}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    {t("finals.rounds.finishTitle")}
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    {t("finals.rounds.finishBody")}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>
                    {t("finals.common.cancel")}
                  </AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => {
                      finish.mutate(undefined, {
                        onSuccess: () => {
                          void navigate(
                            generatePath(paths.finished, {
                              leagueId,
                              tournamentId,
                            }),
                          );
                        },
                      });
                    }}
                  >
                    {t("finals.rounds.finishConfirm")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </section>
      )}
      {latest !== undefined && !hasKnockout && !complete && (
        <Notice
          tone="info"
          title={t("finals.rounds.inProgressTitle", { round: latest.round_no })}
        >
          {t("finals.rounds.inProgressBody", { count: open })}
        </Notice>
      )}
      {hasKnockout && latest !== undefined && (
        <Notice tone="info" title={t("finals.knockout.title")}>
          <p>{t("finals.rounds.knockoutDrawn", { round: latest.round_no })}</p>
          <Link
            to={generatePath(paths.knockout, { leagueId, tournamentId })}
            className="inline-flex min-h-11 items-center font-bold underline underline-offset-4"
          >
            {t("finals.rounds.goToKnockout")}
          </Link>
        </Notice>
      )}
      {latest !== undefined && !hasKnockout && (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              type="button"
              variant="text"
              className="self-start underline"
            >
              {t("finals.rounds.deleteRound", { round: latest.round_no })}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {t("finals.rounds.deleteTitle", { round: latest.round_no })}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {latest.round_no === 1
                  ? t("finals.rounds.deleteBodyFirst")
                  : t("finals.rounds.deleteBody", {
                      previous: latest.round_no - 1,
                    })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t("finals.common.cancel")}</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  removeRound.mutate(latest.id, {
                    onSuccess: () => {
                      setPicked(undefined);
                      if (latest.round_no === 1) {
                        void navigate(
                          generatePath(paths.tournament, {
                            leagueId,
                            tournamentId,
                          }),
                        );
                      }
                    },
                  });
                }}
              >
                {t("finals.rounds.deleteConfirm", { round: latest.round_no })}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </section>
  );

  const standingsHeading =
    qualifiers === null
      ? t("finals.rounds.standings")
      : t("finals.rounds.standingsQualifiers", { count: qualifiers });
  const standingsSection = (
    <section aria-labelledby="standings-heading" className="space-y-3">
      <h2 id="standings-heading" className="font-display text-display-section">
        {standingsHeading}
      </h2>
      <RankingTable
        caption={standingsHeading}
        rows={standings.standings}
        tiebreakers={tiebreakers}
        qualifiers={qualifiers}
        disabled={disabled}
        participants={participants.data ?? []}
        entryName={(entryId) => roster.entry(entryId)}
      />
      <p className="text-caption text-muted-foreground">
        {tiebreakers.length === 0
          ? t("finals.tiebreakers.footnoteNone")
          : t("finals.tiebreakers.footnote", {
              order: list.format(
                tiebreakers.map((key) => t(`finals.tiebreakers.names.${key}`)),
              ),
            })}
      </p>
      <TiebreakerSheet
        leagueId={leagueId}
        tournamentId={tournamentId}
        tiebreakers={tiebreakers}
      />
    </section>
  );

  return (
    <div className="space-y-6">
      <p className="text-body-md text-muted-foreground">
        {t("finals.rounds.summary", {
          date: localDate(data.date),
          entries: entryCount(data.type, mainEntries.length),
        })}
      </p>
      {layout === "desktop" ? (
        <div className="grid grid-cols-2 items-start gap-8">
          {roundsSection}
          {standingsSection}
        </div>
      ) : (
        <>
          {roundsSection}
          {standingsSection}
        </>
      )}
    </div>
  );
}
