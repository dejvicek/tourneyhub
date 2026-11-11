import { useMutation, useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link, useNavigate, useSearchParams } from "react-router";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup } from "@/components/ui/radio-group";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { leagueQueries } from "@/features/leagues/api";
import { setupMutations, setupQueries } from "@/features/tournaments/api";
import { useLayout } from "@/hooks/useLayout";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { dayAndMonth, today } from "./setup/dates";
import { describeError } from "./setup/errors";
import {
  type FormatForm,
  formOf,
  type KnockoutMatchFormat,
  type MatchFormat,
  type TournamentType,
  writeOf,
} from "./setup/format";
import { Notice } from "./setup/Notice";
import { OptionCard } from "./setup/OptionCard";
import { SegmentedControl } from "./setup/SegmentedControl";
import { SetupHeader } from "./setup/SetupPage";
import { SoFarCard } from "./setup/SoFarCard";
import { Stepper } from "./setup/Stepper";
import { typeLabel } from "./setup/summary";
import { newTournamentId } from "./setup/uuid";

const TYPES = ["singles", "doubles", "dyp", "monster_dyp"] as const;

type GroupChoice = "round_robin" | "twice" | "swiss" | "none";
const GROUP_CHOICES = ["round_robin", "twice", "swiss", "none"] as const;

function choiceOf(
  format: Pick<FormatForm, "group_phase" | "round_robin_legs">,
): GroupChoice {
  switch (format.group_phase) {
    case "round_robin":
      return format.round_robin_legs === 2 ? "twice" : "round_robin";
    case "swiss":
      return "swiss";
    case "monster_dyp":
    case "none":
      return "none";
  }
}

/** Screen 2: name, date, type, group phase, formats, goals, fields (FR-030, FR-031, FR-039). */
export function SetupFormatPage() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const editingId = useSearchParams()[0].get("tournament") ?? undefined;
  const settings = useQuery(leagueQueries.detail(leagueId));
  const existing = useQuery(setupQueries.detail(leagueId, editingId));

  const ready =
    settings.data !== undefined &&
    (editingId === undefined || existing.data !== undefined);

  if (!ready) {
    return (
      <section className="mx-auto grid w-full max-w-5xl gap-6">
        <SetupHeader
          step={1}
          title={t("tournaments.setup.format.title")}
          type={existing.data?.format.type}
        />
        <div role="status" className="grid gap-3">
          <span className="sr-only">{t("loading")}</span>
          <Skeleton className="h-24" />
          <Skeleton className="h-48" />
        </div>
      </section>
    );
  }

  const defaults: FormatForm = {
    name: "",
    date: today(),
    type: "dyp",
    group_phase: "round_robin",
    round_robin_legs: 1,
    sit_out_points: 0,
    group_match_format: settings.data.default_match_format,
    knockout_match_format: settings.data.default_match_format,
    final_match_format: null,
    third_place_match: false,
    goals_per_game: settings.data.default_goals_per_game,
    field_count: settings.data.default_field_count,
  };
  return (
    <FormatForm
      key={editingId ?? "new"}
      leagueId={leagueId}
      tournamentId={editingId}
      initial={
        existing.data === undefined
          ? defaults
          : formOf(existing.data.format, settings.data.default_match_format)
      }
      drawsAllowed={settings.data.draws_allowed}
    />
  );
}

interface FormatFormProps {
  leagueId: string;
  /** Set when the tournament exists and the form changes it. */
  tournamentId: string | undefined;
  initial: FormatForm;
  drawsAllowed: boolean;
}

function FormatForm({
  leagueId,
  tournamentId,
  initial,
  drawsAllowed,
}: FormatFormProps) {
  const { t } = useTranslation();
  const layout = useLayout();
  const navigate = useNavigate();
  const nameId = useId();
  const nameHintId = useId();
  const nameErrorId = useId();
  const dateId = useId();
  const typeId = useId();
  const [form, setForm] = useState(initial);
  // A new tournament's name follows the type and the date until it is typed over.
  const [nameEdited, setNameEdited] = useState(tournamentId !== undefined);
  const [nameInvalid, setNameInvalid] = useState(false);
  // The id of a new tournament is made once; a repeated request finds it again.
  const [newId] = useState(newTournamentId);
  const create = useMutation(setupMutations.create(leagueId));
  const change = useMutation(
    setupMutations.format(leagueId, tournamentId ?? ""),
  );
  const saving = tournamentId === undefined ? create : change;

  const name = nameEdited
    ? form.name
    : t("tournaments.setup.format.defaultName", {
        type: typeLabel(t, form.type),
        date: dayAndMonth(form.date),
      });
  const shown: FormatForm = { ...form, name };
  const payload = writeOf(shown);
  const noGroup = form.group_phase === "none";
  const monster = form.type === "monster_dyp";
  const groupChoice = choiceOf(form);

  const patch = (changes: Partial<FormatForm>) => {
    setForm((current) => ({ ...current, ...changes }));
  };
  const chooseType = (type: TournamentType) => {
    patch({
      type,
      group_phase:
        type === "monster_dyp"
          ? "monster_dyp"
          : form.group_phase === "monster_dyp"
            ? "round_robin"
            : form.group_phase,
    });
  };
  const chooseGroup = (choice: GroupChoice) => {
    patch(
      choice === "twice"
        ? { group_phase: "round_robin", round_robin_legs: 2 }
        : choice === "round_robin"
          ? { group_phase: "round_robin", round_robin_legs: 1 }
          : { group_phase: choice },
    );
  };

  const goNext = (id: string) => {
    void navigate(
      generatePath(paths.setupPlayers, { leagueId, tournamentId: id }),
    );
  };
  const submit = () => {
    if (name.trim() === "") {
      setNameInvalid(true);
      document.getElementById(nameId)?.focus();
      return;
    }
    setNameInvalid(false);
    if (tournamentId === undefined) {
      create.mutate(
        { ...payload, id: newId },
        {
          onSuccess: () => {
            goNext(newId);
          },
        },
      );
    } else {
      change.mutate(payload, {
        onSuccess: () => {
          goNext(tournamentId);
        },
      });
    }
  };

  const groupFormats: readonly MatchFormat[] = drawsAllowed
    ? ["bo1", "bo2", "bo3", "bo5"]
    : ["bo1", "bo3", "bo5"];
  const formatText = {
    bo1: t("tournaments.setup.matchFormat.bo1"),
    bo2: t("tournaments.setup.matchFormat.bo2"),
    bo3: t("tournaments.setup.matchFormat.bo3"),
    bo5: t("tournaments.setup.matchFormat.bo5"),
  } satisfies Record<MatchFormat, string>;
  const formatOptions = <Format extends MatchFormat>(
    formats: readonly Format[],
  ) =>
    formats.map((format) => ({
      value: format,
      label: formatText[format],
    }));
  const knockoutFormats: readonly KnockoutMatchFormat[] = ["bo1", "bo3", "bo5"];
  const finalChoice = form.final_match_format ?? "same";

  const content = (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="grid gap-6"
    >
      <div className="grid gap-6 md:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor={nameId}>{t("tournaments.setup.format.name")}</Label>
          <Input
            id={nameId}
            value={name}
            aria-invalid={nameInvalid ? true : undefined}
            aria-describedby={
              nameInvalid ? `${nameHintId} ${nameErrorId}` : nameHintId
            }
            onChange={(event) => {
              setNameEdited(true);
              setNameInvalid(false);
              patch({ name: event.target.value });
            }}
          />
          <p id={nameHintId} className="text-body-sm text-muted-foreground">
            {t("tournaments.setup.format.nameHint")}
          </p>
          {nameInvalid && (
            <p id={nameErrorId} className="text-body-sm text-destructive">
              {t("tournaments.errors.rules.name_required")}
            </p>
          )}
        </div>
        <div className="grid content-start gap-2">
          <Label htmlFor={dateId}>{t("tournaments.setup.format.date")}</Label>
          <Input
            id={dateId}
            type="date"
            value={form.date}
            required
            onChange={(event) => {
              if (event.target.value !== "") {
                patch({ date: event.target.value });
              }
            }}
          />
        </div>
      </div>

      <div className="grid gap-3">
        <span id={typeId} className="text-body-sm font-bold">
          {t("tournaments.setup.format.type")}
        </span>
        <RadioGroup
          value={form.type}
          onValueChange={(next) => {
            const type = TYPES.find((candidate) => candidate === next);
            if (type !== undefined) {
              chooseType(type);
            }
          }}
          aria-labelledby={typeId}
          className="md:grid-cols-2"
        >
          {TYPES.map((type) => (
            <OptionCard
              key={type}
              value={type}
              title={t(`tournaments.setup.type.${type}.title`)}
              description={t(`tournaments.setup.type.${type}.description`)}
            />
          ))}
        </RadioGroup>
      </div>

      {monster ? (
        <Notice
          variant="info"
          title={t("tournaments.setup.format.monsterRounds.title")}
        >
          {t("tournaments.setup.format.monsterRounds.body")}
        </Notice>
      ) : (
        <SegmentedControl
          label={t("tournaments.setup.format.groupPhase")}
          hint={t("tournaments.setup.format.groupPhaseHint")}
          value={groupChoice}
          options={GROUP_CHOICES.map((choice) => ({
            value: choice,
            label: t(`tournaments.setup.groupChoice.${choice}`),
          }))}
          onValueChange={chooseGroup}
        />
      )}

      <section aria-labelledby={`${nameId}-matches`} className="grid gap-5">
        <h2
          id={`${nameId}-matches`}
          className="font-display text-display-section"
        >
          {t("tournaments.setup.format.matchesAndFields")}
        </h2>
        {!noGroup && (
          <SegmentedControl
            label={t(
              `tournaments.setup.format.groupMatches.${form.group_phase}`,
            )}
            hint={
              drawsAllowed
                ? t("tournaments.setup.format.groupMatchesHint")
                : t("tournaments.setup.format.groupMatchesHintNoDraws")
            }
            value={form.group_match_format}
            options={formatOptions(groupFormats)}
            onValueChange={(format) => {
              patch({ group_match_format: format });
            }}
          />
        )}
        {/* A knockout after a group phase is set up when it starts (FR-045). */}
        {noGroup && (
          <>
            <SegmentedControl
              label={t("tournaments.setup.format.knockoutMatches")}
              hint={t("tournaments.setup.format.knockoutMatchesHint")}
              value={form.knockout_match_format}
              options={formatOptions(knockoutFormats)}
              onValueChange={(format) => {
                patch({ knockout_match_format: format });
              }}
            />
            <SegmentedControl
              label={t("tournaments.setup.format.final")}
              value={finalChoice}
              options={[
                {
                  value: "same",
                  label: t("tournaments.setup.format.finalSame"),
                },
                { value: "bo3", label: t("tournaments.setup.matchFormat.bo3") },
                { value: "bo5", label: t("tournaments.setup.matchFormat.bo5") },
              ]}
              onValueChange={(choice) => {
                patch({
                  final_match_format: choice === "same" ? null : choice,
                });
              }}
            />
          </>
        )}
        {noGroup && (
          <SwitchRow
            label={t("tournaments.setup.format.thirdPlace")}
            hint={t("tournaments.setup.format.thirdPlaceHint")}
            checked={form.third_place_match}
            onCheckedChange={(checked) => {
              patch({ third_place_match: checked });
            }}
          />
        )}
        <Stepper
          label={t("tournaments.setup.format.goals")}
          hint={t("tournaments.setup.format.goalsHint")}
          decreaseLabel={t("tournaments.setup.format.goalsLess")}
          increaseLabel={t("tournaments.setup.format.goalsMore")}
          value={form.goals_per_game}
          min={1}
          max={30}
          onValueChange={(goals) => {
            patch({ goals_per_game: goals });
          }}
        />
        <Stepper
          label={t("tournaments.setup.format.fields")}
          hint={t("tournaments.setup.format.fieldsHint")}
          decreaseLabel={t("tournaments.setup.format.fieldsLess")}
          increaseLabel={t("tournaments.setup.format.fieldsMore")}
          value={form.field_count}
          min={1}
          max={16}
          onValueChange={(fields) => {
            patch({ field_count: fields });
          }}
        />
        {!noGroup && (
          <SwitchRow
            label={t("tournaments.setup.format.sitOut")}
            hint={t("tournaments.setup.format.sitOutHint")}
            checked={form.sit_out_points === 1}
            onCheckedChange={(checked) => {
              patch({ sit_out_points: checked ? 1 : 0 });
            }}
          />
        )}
      </section>

      {!noGroup && (
        <Notice
          variant="info"
          title={t("tournaments.setup.format.knockoutLater.title")}
        >
          {t("tournaments.setup.format.knockoutLater.body")}
        </Notice>
      )}

      {saving.isError && (
        <p role="alert" className="text-body-md text-destructive">
          {describeError(saving.error, t)}
        </p>
      )}

      <div className="flex flex-col gap-3 md:flex-row-reverse md:justify-start">
        <Button
          type="submit"
          disabled={saving.isPending}
          size="lg"
          className="md:min-w-60"
        >
          {t("tournaments.setup.format.next")}
        </Button>
        {layout !== "phone" && (
          <Button asChild variant="text" size="lg">
            <Link to={generatePath(paths.tournaments, { leagueId })}>
              {t("tournaments.setup.cancel")}
            </Link>
          </Button>
        )}
      </div>
    </form>
  );

  return (
    <section className="mx-auto grid w-full max-w-5xl gap-6">
      <SetupHeader
        step={1}
        title={t("tournaments.setup.format.title")}
        type={form.type}
      />
      {layout === "desktop" ? (
        <div className="grid grid-cols-[1fr_20rem] items-start gap-8">
          {content}
          <SoFarCard format={shown} />
        </div>
      ) : (
        content
      )}
    </section>
  );
}

interface SwitchRowProps {
  label: string;
  hint: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

/** The design's Toggle row: label and help on the left, the switch on the right. */
function SwitchRow({ label, hint, checked, onCheckedChange }: SwitchRowProps) {
  const labelId = useId();
  const hintId = useId();
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="grid gap-1">
        <span id={labelId} className="text-body-sm font-bold">
          {label}
        </span>
        <p id={hintId} className="text-body-sm text-muted-foreground">
          {hint}
        </p>
      </div>
      <Switch
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-labelledby={labelId}
        aria-describedby={hintId}
      />
    </div>
  );
}
