import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type SubmitEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorCodeOf, validationProblems } from "@/features/auth/apiErrors";

import { leagueMutations } from "./api";
import { SettingsSection } from "./SettingsSection";
import { useSeasonName } from "./useSeasonName";

type SeasonRead = components["schemas"]["SeasonRead"];

/** The most places the API accepts (backend/openapi.json: PlacementPoints). */
const MAX_PLACES = 256;

interface PointsError {
  /** The place (1-based) the message is about; none for the whole table. */
  place?: number;
  message: string;
}

/**
 * FR-011, BR-012: the active season's placement points, one row per place,
 * validated by the server with P5a's rule; the message sits at its place.
 */
export function PlacementPointsForm({
  leagueId,
  season,
  saved,
  onStart,
  onSaved,
}: {
  leagueId: string;
  season: SeasonRead;
  /** Whether this form's save is the last thing that happened on the page. */
  saved: boolean;
  /** A new action starts: the page forgets the last one's news. */
  onStart: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const seasonName = useSeasonName();
  const queryClient = useQueryClient();
  const save = useMutation(
    leagueMutations.setPlacementPoints(queryClient, leagueId),
  );
  const [points, setPoints] = useState(() =>
    season.placement_points.map(String),
  );
  const [local, setLocal] = useState<PointsError | null>(null);

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    onStart();
    save.reset();
    // Parsing is the browser's; the table's rule is the server's (ADR-008).
    const bad = points.findIndex((value) => !/^\d+$/.test(value.trim()));
    if (bad !== -1) {
      setLocal({
        place: bad + 1,
        message: t("leagues.settings.points.notWhole", { place: bad + 1 }),
      });
      return;
    }
    setLocal(null);
    save.mutate(
      { seasonId: season.id, points: points.map(Number) },
      { onSuccess: onSaved },
    );
  }

  const error = local ?? serverError(save.error);

  function serverError(cause: unknown): PointsError | null {
    if (cause === null) {
      return null;
    }
    if (errorCodeOf(cause) === "season_closed") {
      return { message: t("leagues.settings.points.closed") };
    }
    const [problem] = validationProblems(cause);
    if (problem === undefined) {
      return { message: t("leagues.settings.generic") };
    }
    switch (problem.type) {
      case "placement_points_increase": {
        const place = problem.context.place ?? 1;
        return {
          place,
          message: t("leagues.settings.points.increase", { place }),
        };
      }
      case "too_short":
        return { message: t("leagues.settings.points.empty") };
      case "too_long":
        return { message: t("leagues.settings.points.tooMany") };
      default:
        return { message: t("leagues.settings.points.rule") };
    }
  }

  return (
    <SettingsSection
      id="placement-points"
      title={t("leagues.settings.points.heading")}
      description={t("leagues.settings.points.lead", {
        season: seasonName(season),
      })}
    >
      <form noValidate onSubmit={submit} className="space-y-4">
        <p id="points-rule" className="text-body-sm text-muted-foreground">
          {t("leagues.settings.points.rule")}
        </p>
        <ol className="grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-x-4 gap-y-2">
          {points.map((value, index) => {
            const place = index + 1;
            const invalid = error?.place === place;
            return (
              <li key={place} className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="w-8 shrink-0 text-right font-display text-score-m"
                >
                  {t("leagues.settings.points.placeShort", { place })}
                </span>
                <Input
                  aria-label={t("leagues.settings.points.place", { place })}
                  inputMode="numeric"
                  pattern="[0-9]*"
                  value={value}
                  aria-invalid={invalid ? true : undefined}
                  aria-describedby={invalid ? "points-error" : "points-rule"}
                  className="text-base"
                  onChange={(event) => {
                    setPoints((rows) =>
                      rows.map((row, i) =>
                        i === index ? event.target.value : row,
                      ),
                    );
                  }}
                />
              </li>
            );
          })}
        </ol>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={points.length >= MAX_PLACES}
            onClick={() => {
              setPoints((rows) => [...rows, "0"]);
            }}
          >
            {t("leagues.settings.points.add")}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={points.length <= 1}
            onClick={() => {
              setPoints((rows) => rows.slice(0, -1));
            }}
          >
            {t("leagues.settings.points.removeLast")}
          </Button>
        </div>
        <p
          id="points-error"
          role="alert"
          className="text-body-md font-bold text-destructive"
        >
          {error?.message}
        </p>
        {saved && (
          <p role="status" className="text-body-md font-bold text-primary">
            {t("leagues.settings.points.saved")}
          </p>
        )}
        <Button
          type="submit"
          className="w-full sm:w-auto"
          disabled={save.isPending}
        >
          {save.isPending
            ? t("leagues.settings.points.saving")
            : t("leagues.settings.points.save")}
        </Button>
      </form>
    </SettingsSection>
  );
}
