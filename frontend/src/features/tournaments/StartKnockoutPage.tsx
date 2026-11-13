import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  generatePath,
  Link,
  Navigate,
  useNavigate,
  useSearchParams,
} from "react-router";

import type { components } from "@/api/schema";
import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import {
  finalsMutations,
  finalsQueries,
  type PreviewData,
  type TournamentData,
} from "@/features/finals/api";
import { leagueQueries } from "@/features/leagues/api";
import { tournamentQueries } from "@/features/tournaments/api";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";
import { type MonsterKnockoutMode, rules } from "@/lib/rules";
import { cn } from "@/lib/utils";

import { errorText } from "./finals/errorText";
import { localDate, useRoster } from "./finals/names";
import { Notice } from "./finals/Notice";
import { ScreenHeader } from "./finals/ScreenHeader";
import { LoadError, Loading } from "./finals/StateMessage";
import { usePlaceLabel } from "./finals/usePlaceLabel";
import { SegmentedControl } from "./setup/SegmentedControl";

type BracketRoundName = components["schemas"]["RoundName"];
type KnockoutWrite = components["schemas"]["KnockoutWrite"];

const FIRST_ROUND: Record<number, BracketRoundName> = {
  2: "final",
  4: "semifinal",
  8: "quarterfinal",
  16: "round_of_16",
  32: "round_of_32",
  64: "round_of_64",
  128: "round_of_128",
  256: "round_of_256",
};

type KnockoutFormat = NonNullable<KnockoutWrite["match_format"]>;
const KNOCKOUT_FORMATS: readonly KnockoutFormat[] = ["bo1", "bo3", "bo5"];
type FinalChoice = "same" | "bo3" | "bo5";

function isPaired(mode: MonsterKnockoutMode | null): boolean {
  return mode !== null && mode !== "singles";
}

/**
 * Screen 13: configure and draw the knockout after the group phase (FR-045,
 * BR-080–BR-087): how many go through, the third-place match, the match
 * format of the knockout and of the final (BR-120) and, for Monster DYP, how
 * the teams are formed. The preview comes from the draw the server would
 * make; the start carries the phase the screen saw as current (ADR-008).
 */
export function StartKnockoutPage() {
  const { t } = useTranslation();
  return (
    <div className="space-y-6">
      <DocumentTitle screen={t("finals.start.title")} />
      <ScreenHeader title={t("finals.start.title")} />
      <StartKnockoutLoader />
    </div>
  );
}

function StartKnockoutLoader() {
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
  const roundRobin = group.format === "round_robin";
  // BR-080, FR-045: Doubles and DYP entries are pairs, the stepper counts them.
  const pairs = data.type === "doubles" || data.type === "dyp";
  // Screen 8 hands over its choices in the query; a bad value is ignored.
  const [search] = useSearchParams();
  const fromQuery = Number(search.get("qualifiers"));
  const [qualifiers, setQualifiers] = useState(
    Number.isInteger(fromQuery) && fromQuery >= 2
      ? fromQuery
      : (group.qualifiers ?? 8),
  );
  const [thirdPlace, setThirdPlace] = useState(
    search.get("thirdPlace") === "true",
  );
  const [mode, setMode] = useState<MonsterKnockoutMode | null>(
    rules.monsterKnockoutModes[0] ?? null,
  );
  const league = useQuery(leagueQueries.detail(leagueId));
  // BR-120: the knockout plays the league's default unless picked here, and
  // the final the knockout's format unless it has its own.
  const [picked, setPicked] = useState<KnockoutFormat | null>(null);
  const [finalChoice, setFinalChoice] = useState<FinalChoice>("same");
  // What the segmented control shows; the start sends only what was picked,
  // and the server applies the league's default for the rest (BR-120).
  const shownFormat = picked ?? league.data?.default_match_format ?? "bo1";
  const effectiveMode = monster ? mode : null;
  const preview = useQuery({
    ...finalsQueries.preview(leagueId, tournamentId, {
      qualifiers,
      thirdPlaceMatch: thirdPlace,
      mode: effectiveMode,
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
  const groupRounds = data.rounds.filter((r) => r.phase_id === group.id);
  const roundDone =
    groupRounds.length > 0 &&
    (group.format === "round_robin"
      ? groupRounds
      : groupRounds.slice(-1)
    ).every((r) => r.matches.every((m) => m.outcome !== null));
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

  const form = (
    <div className="space-y-6">
      <div
        role="group"
        aria-labelledby="qualifiers-label"
        className="flex items-center gap-3 rounded-lg border border-border-surface bg-card p-4"
      >
        <div className="min-w-0 flex-1">
          <p id="qualifiers-label" className="text-body-md font-bold">
            {t(
              pairs
                ? "finals.start.qualifiersTitlePairs"
                : "finals.start.qualifiersTitle",
            )}
          </p>
          <p className="text-body-sm text-muted-foreground">
            {t(
              monster
                ? "finals.start.qualifiersHelpMonster"
                : "finals.start.qualifiersHelp",
            )}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="icon"
          disabled={shown <= minimum}
          aria-label={t(
            pairs ? "finals.start.decreasePairs" : "finals.start.decrease",
          )}
          onClick={() => {
            changeQualifiers(shown - step);
          }}
        >
          <span aria-hidden="true">−</span>
        </Button>
        <output
          aria-live="polite"
          aria-label={t(
            pairs
              ? "finals.start.qualifiersTitlePairs"
              : "finals.start.qualifiersTitle",
          )}
          className="w-9 text-center font-display text-score-l"
        >
          {shown}
        </output>
        <Button
          type="button"
          variant="outline"
          size="icon"
          disabled={shown >= maximum}
          aria-label={t(
            pairs ? "finals.start.increasePairs" : "finals.start.increase",
          )}
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
            aria-label={t("finals.start.modes")}
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
        </fieldset>
      ) : (
        <p className="text-body-md">
          {t("finals.start.asTheyAre", { count: shown })}
        </p>
      )}

      <SegmentedControl
        label={t("tournaments.setup.format.knockoutMatches")}
        hint={t("tournaments.setup.format.knockoutMatchesHint")}
        value={shownFormat}
        options={KNOCKOUT_FORMATS.map((format) => ({
          value: format,
          label: t(`tournaments.setup.matchFormat.${format}`),
        }))}
        onValueChange={setPicked}
      />
      <SegmentedControl<FinalChoice>
        label={t("tournaments.setup.format.final")}
        value={finalChoice}
        options={[
          { value: "same", label: t("tournaments.setup.format.finalSame") },
          { value: "bo3", label: t("tournaments.setup.matchFormat.bo3") },
          { value: "bo5", label: t("tournaments.setup.matchFormat.bo5") },
        ]}
        onValueChange={setFinalChoice}
      />

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

  const roundKey = FIRST_ROUND[plan.bracket_size ?? 0] ?? "round_of_16";
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
              {entry.decided_by_lot && (
                <span className="text-caption text-muted-foreground">
                  {t("finals.common.byLot")}
                </span>
              )}
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
      {/* BR-053: a knockout locks all of a round robin's results, but only the
          newest round of a Swiss or Monster DYP (BR-087). */}
      {roundRobin ? (
        <Notice tone="warning" title={t("finals.start.lockTitleRoundRobin")}>
          {t("finals.start.lockBodyRoundRobin")}
        </Notice>
      ) : (
        <Notice
          tone="warning"
          title={t("finals.start.lockTitle", { round: plan.locks_round_no })}
        >
          {t("finals.start.lockBody", { round: plan.locks_round_no })}
        </Notice>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <Link
        to={generatePath(paths.betweenRounds, { leagueId, tournamentId })}
        className="inline-flex min-h-11 items-center text-body-md font-bold underline underline-offset-4"
      >
        {t("finals.common.back")}
      </Link>
      <p className="text-body-md text-muted-foreground">
        {t("finals.common.date", { date: localDate(data.date) })}
      </p>
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
        className="w-full lg:w-auto"
        disabled={!canDraw || drawKnockout.isPending}
        onClick={() => {
          drawKnockout.mutate(
            {
              expected_current_phase_id: data.current_phase_id ?? group.id,
              // The draw counter the preview showed (ADR-008).
              expected_draw_counter: plan.draw_counter,
              // The entries the preview shows going through, in seed order.
              expected_qualifier_ids: plan.entries.flatMap((entry) =>
                entry.members.slice(0, 1).map((member) => member.entry_id),
              ),
              qualifiers: shown,
              third_place_match: thirdPlace,
              match_format: picked,
              final_match_format: finalChoice === "same" ? null : finalChoice,
              mode: effectiveMode,
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
