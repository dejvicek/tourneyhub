import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { cn } from "cn";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link, Navigate, useNavigate } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import type { BracketRoundName } from "@/demo/contract";
import { type MonsterKnockoutMode, rules } from "@/demo/rules";
import {
  finalsMutations,
  finalsQueries,
  type PreviewData,
  type TournamentData,
} from "@/features/finals/api";
import { tournamentQueries } from "@/features/tournaments/api";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { errorText } from "./finals/errorText";
import { localDate, useRoster } from "./finals/names";
import { Notice } from "./finals/Notice";
import { ScreenHeader } from "./finals/ScreenHeader";
import { LoadError, Loading } from "./finals/StateMessage";
import { usePlaceLabel } from "./finals/usePlaceLabel";

const FIRST_ROUND: Record<number, BracketRoundName> = {
  2: "final",
  4: "semifinal",
  8: "quarterfinal",
  16: "round_of_16",
};

function isPaired(mode: MonsterKnockoutMode | null): boolean {
  return mode !== null && mode !== "singles";
}

/**
 * Screen 13: configure and draw the knockout after the rounds of a Swiss or
 * Monster DYP (FR-045, BR-080–BR-087): how many go through, the third-place
 * match and, for Monster DYP, how the teams are formed. The preview comes
 * from the draw the server would make.
 */
export function StartKnockoutPage() {
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const data = tournament.data;
  const group = data?.phases.find((phase) => phase.kind === "group");
  if (tournament.isError) {
    return (
      <LoadError
        onRetry={() => {
          void tournament.refetch();
        }}
      />
    );
  }
  if (data === undefined || group === undefined) {
    return <Loading />;
  }
  if (data.phases.some((phase) => phase.kind === "knockout")) {
    return (
      <Navigate
        to={generatePath(paths.knockout, { leagueId, tournamentId })}
        replace
      />
    );
  }
  return (
    <StartKnockoutForm
      leagueId={leagueId}
      tournamentId={tournamentId}
      data={data}
      group={group}
    />
  );
}

interface FormProps {
  leagueId: string;
  tournamentId: string;
  data: TournamentData;
  group: TournamentData["phases"][number];
}

function StartKnockoutForm({ leagueId, tournamentId, data, group }: FormProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const placeLabel = usePlaceLabel();
  const roster = useRoster(leagueId, data.entries);
  const monster = group.format === "monster_dyp";
  const [qualifiers, setQualifiers] = useState(group.qualifiers ?? 8);
  const [thirdPlace, setThirdPlace] = useState(false);
  const [mode, setMode] = useState<MonsterKnockoutMode | null>(
    rules.monsterKnockoutModes[0] ?? null,
  );
  const [draw, setDraw] = useState(0);
  const effectiveMode = monster ? mode : null;
  const preview = useQuery({
    ...finalsQueries.preview(leagueId, tournamentId, {
      qualifiers,
      thirdPlaceMatch: thirdPlace,
      mode: effectiveMode,
      draw,
    }),
    placeholderData: keepPreviousData,
  });
  const drawKnockout = useMutation(
    finalsMutations.drawKnockout(queryClient, leagueId, tournamentId),
  );

  if (preview.isError) {
    return (
      <LoadError
        onRetry={() => {
          void preview.refetch();
        }}
      />
    );
  }
  const plan: PreviewData | undefined = preview.data;
  if (plan === undefined) {
    return <Loading />;
  }

  const paired = isPaired(effectiveMode);
  const step = paired ? 2 : 1;
  const minimum = (paired ? 2 : 1) * (thirdPlace ? 4 : 2);
  const maximum = paired
    ? plan.max_qualifiers - (plan.max_qualifiers % 2)
    : plan.max_qualifiers;
  const shown = plan.qualifiers;
  const half = shown / 2;
  const entriesCount = plan.entries.length;
  const list = new Intl.ListFormat(i18n.resolvedLanguage, {
    style: "short",
    type: "unit",
  });
  const lastRound = data.rounds.filter((r) => r.phase_id === group.id).at(-1);
  const roundDone =
    lastRound?.matches.every((m) => m.outcome !== null) ?? false;
  const canDraw = roundDone && entriesCount >= (thirdPlace ? 4 : 2);
  const mainCount = data.entries.filter((e) => e.stage === "main").length;
  const followers = mainCount - shown;
  const entryLabel = (seed: number): string => {
    const found = plan.entries.find((e) => e.seed === seed);
    const names = (found?.members ?? []).map((m) => roster.entry(m.entry_id));
    const [first, second] = names;
    return first !== undefined && second !== undefined
      ? t("finals.start.pairNames", { first, second })
      : (first ?? "");
  };
  const changeQualifiers = (next: number) => {
    setQualifiers(Math.min(Math.max(next, minimum), maximum));
  };

  const modeText = (m: MonsterKnockoutMode): string => {
    switch (m) {
      case "seeded_pairs": {
        const examples = Array.from({ length: Math.min(half, 4) }, (_, i) =>
          t("finals.start.pairExample", {
            a: placeLabel(i + 1),
            b: placeLabel(half + i + 1),
          }),
        );
        return t("finals.start.modeSeeded", {
          count: shown,
          examples: list.format(examples) + (half > 4 ? " …" : ""),
        });
      }
      case "singles":
        return t("finals.start.modeSingles");
      case "a_little_mercy":
        return t("finals.start.modeMercy", {
          half,
          from: half + 1,
          to: shown,
        });
      case "lord_have_mercy":
        return t("finals.start.modeLord");
    }
  };

  const stepButton = "size-11 p-0 text-button-lg";
  const form = (
    <div className="space-y-6">
      <div
        role="group"
        aria-labelledby="qualifiers-label"
        className="flex items-center gap-3 rounded-lg border border-border-surface bg-card p-4"
      >
        <div className="min-w-0 flex-1">
          <p id="qualifiers-label" className="text-body-md font-bold">
            {t("finals.start.qualifiersTitle")}
          </p>
          <p className="text-body-sm text-muted-foreground">
            {t("finals.start.qualifiersHelp")}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          className={stepButton}
          disabled={shown <= minimum}
          aria-label={t("finals.start.decrease")}
          onClick={() => {
            changeQualifiers(shown - step);
          }}
        >
          <span aria-hidden="true">−</span>
        </Button>
        <output
          aria-live="polite"
          aria-label={t("finals.start.qualifiersValue")}
          className="w-9 text-center font-display text-score-l"
        >
          {shown}
        </output>
        <Button
          type="button"
          variant="outline"
          className={stepButton}
          disabled={shown >= maximum}
          aria-label={t("finals.start.increase")}
          onClick={() => {
            changeQualifiers(shown + step);
          }}
        >
          <span aria-hidden="true">+</span>
        </Button>
      </div>

      <div className="flex items-center gap-3 rounded-lg border border-border-surface bg-card p-4">
        <div className="min-w-0 flex-1">
          <Label htmlFor="third-place" className="text-body-md font-bold">
            {t("finals.start.thirdPlace")}
          </Label>
          <p className="text-body-sm text-muted-foreground">
            {thirdPlace
              ? t("finals.start.thirdPlaceOn")
              : t("finals.start.thirdPlaceOff")}
          </p>
        </div>
        <Switch
          id="third-place"
          checked={thirdPlace}
          onCheckedChange={(on) => {
            setThirdPlace(on);
            if (on) {
              setQualifiers((q) => Math.max(q, (paired ? 2 : 1) * 4));
            }
          }}
        />
      </div>

      {monster ? (
        <fieldset className="space-y-3">
          <legend className="mb-3 font-display text-display-section">
            {t("finals.start.modes")}
          </legend>
          <RadioGroup
            value={effectiveMode ?? undefined}
            onValueChange={(value) => {
              const next = rules.monsterKnockoutModes.find((m) => m === value);
              if (next !== undefined) {
                setMode(next);
                if (isPaired(next) && qualifiers % 2 === 1) {
                  setQualifiers(qualifiers - 1);
                }
              }
            }}
          >
            {rules.monsterKnockoutModes.map((m) => (
              <Label
                key={m}
                htmlFor={`mode-${m}`}
                className={cn(
                  "flex min-h-11 items-start gap-3 rounded-lg border-2 border-border-surface bg-card p-4 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-notice-info",
                )}
              >
                <RadioGroupItem value={m} id={`mode-${m}`} className="mt-0.5" />
                <span className="space-y-1">
                  <span className="block text-body-md font-bold">
                    {t(`tournaments.knockoutModes.${m}`)}
                  </span>
                  <span className="block text-body-sm text-muted-foreground">
                    {modeText(m)}
                  </span>
                </span>
              </Label>
            ))}
          </RadioGroup>
          {(effectiveMode === "a_little_mercy" ||
            effectiveMode === "lord_have_mercy") && (
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              onClick={() => {
                setDraw((d) => d + 1);
              }}
            >
              {t("finals.start.drawAgain")}
            </Button>
          )}
        </fieldset>
      ) : (
        <p className="text-body-md">
          {t("finals.start.asTheyAre", { count: shown })}
        </p>
      )}

      {plan.skipped_entry_ids.length > 0 && (
        <Notice
          tone="info"
          title={t("finals.start.skippedTitle", {
            count: plan.skipped_entry_ids.length,
            names: list.format(
              plan.skipped_entry_ids.map((id) => roster.entry(id)),
            ),
          })}
        >
          {t("finals.start.skippedBody")}
        </Notice>
      )}
    </div>
  );

  const roundKey = FIRST_ROUND[plan.bracket_size] ?? "round_of_16";
  const previewColumn = (
    <div className="space-y-6">
      <section aria-labelledby="preview-heading" className="space-y-2">
        <h2 id="preview-heading" className="font-display text-display-section">
          {t("finals.start.preview")}
        </h2>
        <ol className="border-t border-border">
          {plan.entries.map((entry) => (
            <li
              key={entry.seed}
              className="flex items-center gap-3 border-b border-border py-2.5"
            >
              <span className="w-6 font-display text-score-s">
                {entry.seed}
              </span>
              <span className="flex-1 text-body-md font-bold">
                {entryLabel(entry.seed)}
              </span>
              <span className="text-body-sm text-muted-foreground">
                {entry.members.length === 2 &&
                entry.members[0] &&
                entry.members[1]
                  ? t("finals.start.previewPlaces", {
                      first: placeLabel(entry.members[0].place),
                      second: placeLabel(entry.members[1].place),
                    })
                  : placeLabel(entry.members[0]?.place ?? 0)}
              </span>
            </li>
          ))}
        </ol>
      </section>
      <section aria-labelledby="first-round-heading" className="space-y-2">
        <h2
          id="first-round-heading"
          className="font-display text-display-section"
        >
          {t(`finals.start.firstRound.${roundKey}`)}
        </h2>
        <ul className="space-y-2">
          {plan.first_round.map(([first, b]) => {
            const a = first ?? 0;
            return (
              <li
                key={a}
                className="flex items-center gap-3 rounded-lg border border-border-surface bg-card p-3 text-body-sm"
              >
                <span className="flex-1 font-bold">{entryLabel(a)}</span>
                {b === null || b === undefined ? (
                  <span className="text-muted-foreground">
                    {t("finals.start.bye")}
                  </span>
                ) : (
                  <>
                    <span
                      aria-hidden="true"
                      className="text-caption font-bold text-muted-foreground"
                    >
                      {t("finals.start.versus")}
                    </span>
                    <span className="sr-only">
                      {t("finals.start.versusLong")}
                    </span>
                    <span className="flex-1 text-end font-bold">
                      {entryLabel(b)}
                    </span>
                  </>
                )}
              </li>
            );
          })}
        </ul>
        {followers > 0 && (
          <p className="text-caption text-muted-foreground">
            {t("finals.start.followLead", {
              from: entriesCount + 1,
              to: entriesCount + followers,
            })}
          </p>
        )}
      </section>
      <Notice
        tone="warning"
        title={t("finals.start.lockTitle", { round: plan.locks_round_no })}
      >
        {t("finals.start.lockBody", { round: plan.locks_round_no })}
      </Notice>
    </div>
  );

  return (
    <div className="space-y-6">
      <DocumentTitle screen={`${data.name} · ${t("finals.start.title")}`} />
      <Link
        to={generatePath(paths.betweenRounds, { leagueId, tournamentId })}
        className="inline-flex min-h-11 items-center text-body-md font-bold underline underline-offset-4"
      >
        {t("finals.common.back")}
      </Link>
      <ScreenHeader
        title={t("finals.start.title")}
        subtitle={`${data.name}, ${t("finals.common.date", { date: localDate(data.date) })}`}
      />
      {!roundDone && (
        <Notice tone="warning" title={t("finals.common.notReady")} />
      )}
      <div className="grid gap-6 lg:grid-cols-2 lg:items-start lg:gap-8">
        <div className="md:grid md:grid-cols-1">{form}</div>
        {previewColumn}
      </div>
      {tooFew(entriesCount, thirdPlace) && (
        <p role="alert" className="text-body-sm">
          {t("finals.start.tooFew")}
        </p>
      )}
      {drawKnockout.isError && (
        <p role="alert" className="text-body-sm">
          {errorText(t, drawKnockout.error)}
        </p>
      )}
      <Button
        type="button"
        size="lg"
        className="min-h-14 w-full text-button-lg lg:w-auto"
        disabled={!canDraw || drawKnockout.isPending}
        onClick={() => {
          drawKnockout.mutate(
            {
              qualifiers: shown,
              third_place_match: thirdPlace,
              mode: effectiveMode,
              draw,
            },
            {
              onSuccess: () => {
                void navigate(
                  generatePath(paths.knockout, { leagueId, tournamentId }),
                );
              },
            },
          );
        }}
      >
        {t("finals.start.draw")}
      </Button>
    </div>
  );
}

function tooFew(entries: number, thirdPlace: boolean): boolean {
  return entries < (thirdPlace ? 4 : 2);
}
