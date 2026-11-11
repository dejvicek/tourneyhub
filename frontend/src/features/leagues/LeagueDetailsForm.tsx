import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import { fieldErrors } from "@/features/auth/fieldErrors";
import { FormField } from "@/features/auth/FormField";

import { leagueMutations } from "./api";
import { SettingsSection } from "./SettingsSection";
import { Stepper } from "./Stepper";

type DefaultMatchFormat = components["schemas"]["DefaultMatchFormat"];
type LeagueRead = components["schemas"]["LeagueRead"];

/** The API's bounds (backend/openapi.json: LeagueName, LeagueUpdate). */
const MAX_NAME_LENGTH = 100;
const MAX_FIELDS = 32;
const MAX_GOALS = 99;

const FORMATS = ["bo1", "bo3", "bo5"] as const satisfies DefaultMatchFormat[];

function isFormat(value: string): value is DefaultMatchFormat {
  return FORMATS.some((format) => format === value);
}

/**
 * FR-011: the league's name, draws and the defaults of new tournaments, saved
 * together as target states (P5a's PATCH, ADR-008).
 */
export function LeagueDetailsForm({
  league,
  saved,
  onStart,
  onSaved,
}: {
  league: LeagueRead;
  /** Whether this form's save is the last thing that happened on the page. */
  saved: boolean;
  /** A new action starts: the page forgets the last one's news. */
  onStart: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const update = useMutation(leagueMutations.update(queryClient, league.id));
  const [name, setName] = useState(league.name);
  const [draws, setDraws] = useState(league.draws_allowed);
  const [fields, setFields] = useState(String(league.default_field_count));
  const [format, setFormat] = useState(league.default_match_format);
  const [goals, setGoals] = useState(String(league.default_goals_per_game));
  const [local, setLocal] = useState<Partial<Record<string, string>>>({});

  /** A count from 1 to `max`, or the message why not (browser-only parsing). */
  function count(value: string, max: number): number | string {
    if (!/^\d+$/.test(value.trim())) {
      return t("leagues.settings.league.wholeNumber");
    }
    const number = Number(value);
    if (number < 1) {
      return t("leagues.settings.league.atLeastOne");
    }
    return number > max ? t("auth.errors.tooLarge", { count: max }) : number;
  }

  function submit() {
    onStart();
    update.reset();
    const fieldCount = count(fields, MAX_FIELDS);
    const goalCount = count(goals, MAX_GOALS);
    const nameProblem =
      name.trim().length > MAX_NAME_LENGTH
        ? t("auth.errors.nameTooLong", { count: MAX_NAME_LENGTH })
        : undefined;
    if (
      nameProblem !== undefined ||
      typeof fieldCount === "string" ||
      typeof goalCount === "string"
    ) {
      setLocal({
        name: nameProblem,
        default_field_count:
          typeof fieldCount === "string" ? fieldCount : undefined,
        default_goals_per_game:
          typeof goalCount === "string" ? goalCount : undefined,
      });
      return;
    }
    setLocal({});
    update.mutate(
      {
        name,
        draws_allowed: draws,
        default_field_count: fieldCount,
        default_match_format: format,
        default_goals_per_game: goalCount,
      },
      { onSuccess: onSaved },
    );
  }

  const server = fieldErrors(t, update.error);
  const errors = { ...server, ...local };
  const failed =
    update.isError && Object.values(server).every((v) => v === undefined);

  return (
    <SettingsSection
      id="league-details"
      title={t("leagues.settings.league.heading")}
    >
      {/* No <form>: Radix's switch and radios render hidden inputs that need
          ResizeObserver inside one; the values are state, saved by the button. */}
      <div className="space-y-6">
        <FormField
          label={t("leagues.settings.league.name")}
          name="name"
          autoComplete="off"
          required
          maxLength={MAX_NAME_LENGTH}
          value={name}
          error={errors.name}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <Label htmlFor="draws-allowed" className="text-body-md">
              {t("leagues.settings.league.draws")}
            </Label>
            <p id="draws-hint" className="text-body-sm text-muted-foreground">
              {t("leagues.settings.league.drawsHint")}
            </p>
          </div>
          <Switch
            id="draws-allowed"
            checked={draws}
            aria-describedby="draws-hint"
            className="mt-1"
            onCheckedChange={setDraws}
          />
        </div>
        <fieldset className="space-y-4">
          <legend className="mb-3 text-body-md font-bold">
            {t("leagues.settings.league.defaultsHeading")}
          </legend>
          <div className="grid gap-4 sm:grid-cols-2">
            <Stepper
              label={t("leagues.settings.league.fields")}
              hint={t("leagues.settings.league.fieldsHint")}
              value={fields}
              max={MAX_FIELDS}
              error={errors.default_field_count}
              onChange={setFields}
            />
            <Stepper
              label={t("leagues.settings.league.goals")}
              value={goals}
              max={MAX_GOALS}
              error={errors.default_goals_per_game}
              onChange={setGoals}
            />
          </div>
          <div className="space-y-2">
            <p id="format-label" className="text-body-sm font-bold">
              {t("leagues.settings.league.format")}
            </p>
            <RadioGroup
              aria-labelledby="format-label"
              value={format}
              onValueChange={(value) => {
                if (isFormat(value)) {
                  setFormat(value);
                }
              }}
              className="grid-cols-3 gap-2"
            >
              {FORMATS.map((option) => (
                <Label
                  key={option}
                  htmlFor={`format-${option}`}
                  className="flex min-h-14 cursor-pointer flex-col items-start gap-1 rounded-lg border-2 border-border-surface px-3 py-2 has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-notice-info"
                >
                  <span className="flex items-center gap-2">
                    <RadioGroupItem id={`format-${option}`} value={option} />
                    <span className="text-body-md font-bold">
                      {t(`leagues.settings.formats.${option}`)}
                    </span>
                  </span>
                  <span className="text-caption font-normal text-muted-foreground">
                    {t(`leagues.settings.formats.${option}Hint`)}
                  </span>
                </Label>
              ))}
            </RadioGroup>
          </div>
        </fieldset>
        <p role="alert" className="text-body-md font-bold text-destructive">
          {failed ? t("leagues.settings.generic") : undefined}
        </p>
        {/* Rendered only with its message: the desktop sidebar has a status too. */}
        {saved && (
          <p role="status" className="text-body-md font-bold text-primary">
            {t("leagues.settings.league.saved")}
          </p>
        )}
        <Button
          type="button"
          onClick={submit}
          className="w-full sm:w-auto"
          disabled={update.isPending}
        >
          {update.isPending
            ? t("leagues.settings.league.saving")
            : t("leagues.settings.league.save")}
        </Button>
      </div>
    </SettingsSection>
  );
}
