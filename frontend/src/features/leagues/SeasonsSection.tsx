import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type SubmitEvent, useState } from "react";
import { useTranslation } from "react-i18next";

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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { errorCodeOf } from "@/features/auth/apiErrors";
import { fieldErrors } from "@/features/auth/fieldErrors";
import { FormField } from "@/features/auth/FormField";

import { leagueMutations, leagueQueries } from "./api";
import { SettingsSection } from "./SettingsSection";
import { useSeasonName } from "./useSeasonName";

type SeasonRead = components["schemas"]["SeasonRead"];

/**
 * FR-020–FR-022: the active season, renamed or followed by a new one, and the
 * closed ones, read-only except their name (BR-011).
 */
export function SeasonsSection({
  leagueId,
  seasons,
}: {
  leagueId: string;
  seasons: SeasonRead[];
}) {
  const { t } = useTranslation();
  const active = seasons.find((season) => season.state === "active");
  const closed = seasons
    .filter((season) => season.state === "closed")
    .sort((a, b) => b.number - a.number);

  return (
    <SettingsSection id="seasons" title={t("leagues.settings.seasons.heading")}>
      {active !== undefined && (
        <div className="space-y-4">
          <SeasonRow leagueId={leagueId} season={active} />
          <StartSeason leagueId={leagueId} active={active} />
        </div>
      )}
      {closed.length > 0 && (
        <div className="space-y-2 border-t border-border pt-4">
          <p className="text-body-sm text-muted-foreground">
            {t("leagues.settings.seasons.readOnly")}
          </p>
          <ul className="divide-y divide-border">
            {closed.map((season) => (
              <li key={season.id}>
                <SeasonRow leagueId={leagueId} season={season} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </SettingsSection>
  );
}

function useDate() {
  const { i18n } = useTranslation();
  const format = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    dateStyle: "medium",
  });
  return (iso: string) => format.format(new Date(iso));
}

function SeasonRow({
  leagueId,
  season,
}: {
  leagueId: string;
  season: SeasonRead;
}) {
  const { t } = useTranslation();
  const seasonName = useSeasonName();
  const date = useDate();
  const name = seasonName(season);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-2">
      <div className="min-w-0 space-y-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-display text-display-name break-words">
            {name}
          </span>
          <Badge variant={season.state === "active" ? "default" : "secondary"}>
            {season.state === "active"
              ? t("leagues.settings.seasons.active")
              : t("leagues.settings.seasons.closed")}
          </Badge>
        </p>
        <p className="text-body-sm text-muted-foreground">
          {season.closed_at === null
            ? t("leagues.settings.seasons.started", {
                date: date(season.started_at),
              })
            : t("leagues.settings.seasons.closedOn", {
                start: date(season.started_at),
                end: date(season.closed_at),
              })}
        </p>
        {season.state === "closed" && (
          <p className="text-body-sm text-muted-foreground">
            {t("leagues.settings.seasons.pointsOf", {
              points: season.placement_points.join(", "),
            })}
          </p>
        )}
      </div>
      <RenameSeason leagueId={leagueId} season={season} name={name} />
    </div>
  );
}

/** The API's longest season name, in characters (SeasonName). */
const MAX_NAME_LENGTH = 100;

function RenameSeason({
  leagueId,
  season,
  name,
}: {
  leagueId: string;
  season: SeasonRead;
  name: string;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const rename = useMutation(
    leagueMutations.renameSeason(queryClient, leagueId),
  );
  const [open, setOpen] = useState(false);
  const [tooLong, setTooLong] = useState(false);
  const defaultName = t("shell.seasonName", { number: season.number });

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("name");
    const text = typeof value === "string" ? value.trim() : "";
    // The API's SeasonName allows 100 characters (a paste can pass maxLength).
    setTooLong(text.length > MAX_NAME_LENGTH);
    if (text.length > MAX_NAME_LENGTH) {
      rename.reset();
      return;
    }
    rename.mutate(
      // FR-020: empty restores the default name.
      { seasonId: season.id, name: text === "" ? null : text },
      {
        onSuccess: () => {
          setOpen(false);
        },
      },
    );
  }

  const errors = fieldErrors(t, rename.error);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setTooLong(false);
        rename.reset();
      }}
    >
      <Button
        type="button"
        variant="outline"
        aria-label={t("leagues.settings.seasons.renameTitle", { season: name })}
        onClick={() => {
          setOpen(true);
        }}
      >
        {t("leagues.settings.seasons.rename")}
      </Button>
      <DialogContent>
        <form noValidate onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>
              {t("leagues.settings.seasons.renameTitle", { season: name })}
            </DialogTitle>
          </DialogHeader>
          <FormField
            label={t("leagues.settings.seasons.name")}
            name="name"
            autoComplete="off"
            maxLength={MAX_NAME_LENGTH}
            defaultValue={season.name ?? ""}
            placeholder={defaultName}
            hint={t("leagues.settings.seasons.nameHint", { defaultName })}
            error={
              (tooLong
                ? t("auth.errors.nameTooLong", { count: MAX_NAME_LENGTH })
                : undefined) ??
              errors.name ??
              (rename.isError ? t("leagues.settings.generic") : undefined)
            }
          />
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setOpen(false);
              }}
            >
              {t("leagues.settings.seasons.cancel")}
            </Button>
            <Button type="submit" disabled={rename.isPending}>
              {t("leagues.settings.seasons.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * FR-021: closes the active season and starts the next, carrying the number
 * this screen saw (ADR-008). BR-010 keeps it shut while a tournament of the
 * season is unfinished; the screen says which, the server checks it too.
 */
function StartSeason({
  leagueId,
  active,
}: {
  leagueId: string;
  active: SeasonRead;
}) {
  const { t } = useTranslation();
  const seasonName = useSeasonName();
  const queryClient = useQueryClient();
  const start = useMutation(leagueMutations.startSeason(queryClient, leagueId));
  const tournaments = useQuery(leagueQueries.tournaments(leagueId, active.id));
  const [outcome, setOutcome] = useState<string | null>(null);
  const unfinished = (tournaments.data ?? []).filter(
    (tournament) => tournament.state !== "finished",
  );
  const current = seasonName(active);
  const next = t("shell.seasonName", { number: active.number + 1 });
  const blocked = unfinished.length > 0;

  return (
    <div className="space-y-2">
      {blocked && (
        <p className="rounded-lg bg-notice-warning px-4 py-3.5 text-body-md text-notice-warning-foreground">
          {t("leagues.settings.seasons.startBlocked", {
            count: unfinished.length,
            names: unfinished.map((tournament) => tournament.name).join(", "),
          })}
        </p>
      )}
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            type="button"
            variant="outline"
            className="w-full sm:w-auto"
            disabled={blocked || tournaments.isPending || start.isPending}
          >
            {t("leagues.settings.seasons.start", { season: next })}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("leagues.settings.seasons.startTitle", { next })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("leagues.settings.seasons.startBody", { current, next })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t("leagues.settings.seasons.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setOutcome(null);
                start.mutate(active.number, {
                  onSuccess: (season) => {
                    setOutcome(
                      t("leagues.settings.seasons.startedNew", {
                        season: seasonName(season),
                      }),
                    );
                  },
                  onError: (error) => {
                    const number = error.detail.current_number;
                    setOutcome(
                      errorCodeOf(error) === "season_number_changed" &&
                        typeof number === "number"
                        ? t("leagues.settings.seasons.changed", { number })
                        : t("leagues.settings.generic"),
                    );
                  },
                });
              }}
            >
              {t("leagues.settings.seasons.startConfirm", { current })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {outcome !== null && (
        <p role="status" className="text-body-md font-bold">
          {outcome}
        </p>
      )}
    </div>
  );
}
