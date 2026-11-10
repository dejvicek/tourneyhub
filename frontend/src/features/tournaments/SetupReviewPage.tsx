import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link, useNavigate } from "react-router";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { leagueQueries } from "@/features/leagues/api";
import {
  type SchedulePreviewData,
  setupMutations,
  setupQueries,
} from "@/features/tournaments/api";
import { useLayout } from "@/hooks/useLayout";
import { paths } from "@/lib/paths";

import { describeError, isChanged } from "./setup/errors";
import { Notice } from "./setup/Notice";
import { type SetupData, SetupPage } from "./setup/SetupPage";
import {
  dateLabel,
  entryName,
  formatLabel,
  groupPhaseLabel,
  sitOutLabel,
  typeLabel,
} from "./setup/summary";
import { SummaryRow } from "./setup/SummaryRow";

/** Screen 5: the summary, the first round, "Generate and start" (FR-035, FR-036). */
export function SetupReviewPage() {
  const { t } = useTranslation();
  return (
    <SetupPage step={4} title={() => t("tournaments.setup.review.title")}>
      {(data) => <Review data={data} />}
    </SetupPage>
  );
}

function Review({ data }: { data: SetupData }) {
  const { t } = useTranslation();
  const layout = useLayout();
  const navigate = useNavigate();
  const { leagueId, tournamentId, tournament, setup, nameOf } = data;
  const format = setup.format;
  const settings = useQuery(leagueQueries.settings(leagueId));
  const preview = useQuery(setupQueries.preview(leagueId, tournamentId));
  // Once the tournament is started this screen unmounts (the gate in
  // SetupPage), so the way on is not a per-call callback: it waits for the
  // reload, then opens the tournament on the screen for its state.
  const start = useMutation({
    ...setupMutations.start(leagueId, tournamentId),
    onSuccess: async (_data, _counter, _result, context) => {
      await context.client.invalidateQueries({
        queryKey: ["leagues", leagueId],
      });
      void navigate(generatePath(paths.tournament, params));
    },
  });
  const params = { leagueId, tournamentId };

  const entries = tournament.entries.filter((entry) => entry.stage === "main");
  const noGroup = format.group_phase === "none";
  const roundRobin = format.group_phase === "round_robin";
  const rounds = preview.data?.rounds ?? [];
  const matchCount = preview.data?.match_count ?? null;
  const roundCount = preview.data?.round_count ?? null;
  const sides = (ids: readonly string[]) => ids.map(nameOf);

  const entryRow = (() => {
    switch (tournament.type) {
      case "dyp":
        return t("tournaments.setup.review.pairsDrawn", {
          count: entries.length,
          players: setup.player_ids.length,
        });
      case "doubles":
        return t("tournaments.setup.review.pairsMade", {
          count: entries.length,
        });
      case "singles":
      case "monster_dyp":
        return t("tournaments.setup.review.players", {
          count: setup.player_ids.length,
        });
    }
  })();
  const matchesRow = (() => {
    if (preview.data === undefined) {
      return t("loading");
    }
    if (matchCount === null) {
      return t("tournaments.setup.review.matchesOpen", {
        format: formatLabel(
          t,
          format.group_phase === "none"
            ? format.knockout_match_format
            : format.group_match_format,
        ),
      });
    }
    if (noGroup) {
      return t("tournaments.setup.review.matchesKnockout", {
        count: matchCount,
        format: formatLabel(t, format.knockout_match_format),
      });
    }
    return t("tournaments.setup.review.matches", {
      count: matchCount,
      rounds: roundCount ?? 0,
      format: formatLabel(t, format.group_match_format),
    });
  })();

  const summary = (
    <Card>
      <CardContent>
        <dl>
          <SummaryRow label={t("tournaments.setup.summary.name")}>
            {tournament.name}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.date")}>
            {dateLabel(tournament.date)}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.type")}>
            {typeLabel(t, tournament.type)}
          </SummaryRow>
          <SummaryRow
            label={
              tournament.type === "singles" || tournament.type === "monster_dyp"
                ? t("tournaments.setup.summary.playersLabel")
                : t("tournaments.setup.summary.pairs")
            }
          >
            {entryRow}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.groupPhase")}>
            {groupPhaseLabel(t, format)}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.matches")}>
            {matchesRow}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.final")}>
            {format.final_match_format === null
              ? t("tournaments.setup.format.finalSame")
              : formatLabel(t, format.final_match_format)}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.goals")}>
            {format.goals_per_game}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.fields")}>
            {format.field_count}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.draws")}>
            {settings.data?.draws_allowed
              ? t("tournaments.setup.review.drawsAllowed")
              : t("tournaments.setup.review.drawsNotAllowed")}
          </SummaryRow>
          {!noGroup && (
            <SummaryRow label={t("tournaments.setup.summary.sitOut")}>
              {sitOutLabel(t, format.sit_out_points === 1)}
            </SummaryRow>
          )}
          <SummaryRow label={t("tournaments.setup.summary.knockout")}>
            {noGroup
              ? t("tournaments.setup.review.knockoutNow")
              : t("tournaments.setup.review.knockoutLater")}
          </SummaryRow>
        </dl>
      </CardContent>
    </Card>
  );

  const visibleRounds: SchedulePreviewData["rounds"] =
    layout === "phone" ? rounds.slice(0, 1) : rounds;
  const lastRound = rounds.length;
  const sitting = rounds.some((round) => round.sitting_out.length > 0);
  const schedule = (
    <section
      aria-labelledby="schedule-heading"
      className="grid content-start gap-3"
    >
      <h2 id="schedule-heading" className="font-display text-display-section">
        {layout === "phone" || !roundRobin
          ? t("tournaments.setup.review.firstRound")
          : t("tournaments.setup.review.schedule")}
      </h2>
      {preview.isError && (
        <p role="alert" className="text-body-md text-destructive">
          {t("tournaments.errors.load")}
        </p>
      )}
      {visibleRounds.map((round) => (
        <div key={round.round_no} className="grid gap-2">
          {layout !== "phone" && roundRobin && (
            <h3 className="text-body-md font-bold">
              {t("tournaments.setup.review.round", { round: round.round_no })}
            </h3>
          )}
          <ul className="grid gap-2">
            {round.matches.map((match) => (
              <li
                key={match.sides.flat().join("+")}
                className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-lg border border-border-surface bg-card p-3"
              >
                <MatchSide names={sides(match.sides[0] ?? [])} />
                <span className="text-caption font-bold text-muted-foreground">
                  {t("tournaments.setup.review.versus")}
                </span>
                <MatchSide names={sides(match.sides[1] ?? [])} alignEnd />
              </li>
            ))}
          </ul>
          {round.sitting_out.length > 0 && (
            <p className="text-body-sm text-muted-foreground">
              {t("tournaments.setup.review.sitsOut", {
                names: round.sitting_out
                  .map((ids) => entryName(t, sides(ids)))
                  .join(", "),
              })}
            </p>
          )}
        </div>
      ))}
      <div className="grid gap-1 text-body-sm text-muted-foreground">
        {roundRobin ? (
          <>
            {layout === "phone" && lastRound > 2 && (
              <p>
                {t("tournaments.setup.review.roundsFollow", {
                  last: lastRound,
                })}
              </p>
            )}
            {layout === "phone" && lastRound === 2 && (
              <p>{t("tournaments.setup.review.roundFollows")}</p>
            )}
            <p>
              {sitting
                ? t("tournaments.setup.review.somebodySits")
                : t("tournaments.setup.review.nobodySits")}
            </p>
          </>
        ) : (
          <p>
            {noGroup
              ? t("tournaments.setup.review.bracketNote", {
                  size: preview.data?.bracket_size ?? 0,
                })
              : t("tournaments.setup.review.nextRoundsNote")}
          </p>
        )}
      </div>
    </section>
  );

  return (
    <div className="grid gap-6">
      <div className="grid gap-6 md:grid-cols-2 md:items-start">
        {summary}
        {schedule}
      </div>
      <Notice
        variant="info"
        title={t("tournaments.setup.review.canChange.title")}
      >
        {t("tournaments.setup.review.canChange.body")}
      </Notice>
      {start.isError && (
        <p
          role={isChanged(start.error) ? "status" : "alert"}
          className="text-body-md text-destructive"
        >
          {describeError(start.error, t)}
        </p>
      )}
      <div className="flex flex-col gap-3 md:flex-row md:justify-between">
        <Button asChild variant="text" size="lg">
          <Link to={generatePath(paths.setupDraw, params)}>
            {t("tournaments.setup.back")}
          </Link>
        </Button>
        <Button
          type="button"
          disabled={start.isPending || preview.data === undefined}
          size="lg"
          className="md:min-w-60"
          onClick={() => {
            start.mutate(setup.draw_counter);
          }}
        >
          {t("tournaments.setup.review.start")}
        </Button>
      </div>
    </div>
  );
}

function MatchSide({
  names,
  alignEnd = false,
}: {
  names: readonly string[];
  alignEnd?: boolean;
}) {
  return (
    <span
      className={`grid text-body-md font-bold ${alignEnd ? "text-right" : ""}`}
    >
      {names.map((name, index) => (
        <span key={`${String(index)}${name}`}>{name}</span>
      ))}
    </span>
  );
}
