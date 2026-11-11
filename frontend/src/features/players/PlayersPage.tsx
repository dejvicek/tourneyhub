import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type KeyboardEvent, type SubmitEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import type { components } from "@/api/schema";
import { DocumentTitle } from "@/components/DocumentTitle";
import { PageFallback } from "@/components/PageFallback";
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
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorCodeOf, ruleOf } from "@/features/auth/apiErrors";
import { fieldErrors } from "@/features/auth/fieldErrors";
import { FormField } from "@/features/auth/FormField";
import { EmptyState } from "@/features/leagues/EmptyState";
import { useRouteParam } from "@/hooks/useRouteParam";

import { playerMutations, playerQueries } from "./api";

type PlayerRead = components["schemas"]["PlayerRead"];

/** The API's longest name, in characters (PlayerName). */
const MAX_NAME_LENGTH = 100;

/**
 * The league's player list (FR-012): add, rename, remove and restore, with
 * names unique whatever the letter case (BR-001). Removed players keep their
 * history and wait below the list (BR-002).
 */
export function PlayersPage() {
  const { t, i18n } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const players = useQuery(playerQueries.list(leagueId));
  const [announcement, setAnnouncement] = useState("");
  const collator = new Intl.Collator(i18n.resolvedLanguage);
  const sorted = [...(players.data ?? [])].sort((a, b) =>
    collator.compare(a.name, b.name),
  );
  const active = sorted.filter((player) => player.removed_at === null);
  const removed = sorted.filter((player) => player.removed_at !== null);

  return (
    <section className="space-y-6">
      <DocumentTitle screen={t("players.list.title")} />
      <header className="space-y-2">
        <h1 className="font-display text-display-title">
          {t("players.list.title")}
        </h1>
        <p className="text-body-md text-muted-foreground">
          {t("players.list.lead")}
        </p>
      </header>
      <AddPlayer leagueId={leagueId} onDone={setAnnouncement} />
      <p
        role="status"
        className="text-body-md font-bold break-words text-primary"
      >
        {announcement}
      </p>
      {players.isPending ? (
        <PageFallback />
      ) : players.isError ? (
        <p role="alert" className="text-body-md">
          {t("players.list.loadFailed")}
        </p>
      ) : active.length === 0 ? (
        <EmptyState
          title={t("players.list.empty")}
          body={t("players.list.emptyBody")}
        />
      ) : (
        <section aria-labelledby="players-count" className="space-y-2">
          <h2
            id="players-count"
            className="text-body-sm font-bold text-muted-foreground"
          >
            {t("players.list.count", { count: active.length })}
          </h2>
          <ul className="rounded-lg border border-border-surface bg-card px-4 text-card-foreground md:columns-2 md:gap-8">
            {active.map((player) => (
              <PlayerRow
                key={player.id}
                leagueId={leagueId}
                player={player}
                onDone={setAnnouncement}
              />
            ))}
          </ul>
        </section>
      )}
      {removed.length > 0 && (
        <section aria-labelledby="removed-players" className="space-y-2">
          <h2
            id="removed-players"
            className="text-body-sm font-bold text-muted-foreground"
          >
            {t("players.removed.heading", { count: removed.length })}
          </h2>
          <ul className="rounded-lg border border-dashed border-border px-4">
            {removed.map((player) => (
              <RemovedRow
                key={player.id}
                leagueId={leagueId}
                player={player}
                onDone={setAnnouncement}
              />
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}

/** The message for a taken name (BR-001), or undefined for other errors. */
function useNameTaken() {
  const { t } = useTranslation();
  return (error: unknown): string | undefined => {
    if (
      errorCodeOf(error) !== "player_name_taken" ||
      !(error instanceof ApiError)
    ) {
      return undefined;
    }
    const name = typeof error.detail.name === "string" ? error.detail.name : "";
    // The API: the 409 of a race has no detail; the reload shows the holder.
    if (name === "") {
      return t("players.errors.takenUnknown");
    }
    return error.detail.removed === true
      ? t("players.errors.takenRemoved", { name })
      : t("players.errors.taken", { name });
  };
}

function AddPlayer({
  leagueId,
  onDone,
}: {
  leagueId: string;
  onDone: (message: string) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const add = useMutation(playerMutations.add(queryClient, leagueId));
  const restore = useMutation(
    playerMutations.setRemoved(queryClient, leagueId),
  );
  const nameTaken = useNameTaken();
  const [name, setName] = useState("");
  const [tooLong, setTooLong] = useState(false);

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    // A new action: the last one's news is old (it clears even on failure).
    onDone("");
    restore.reset();
    if (name.trim().length > MAX_NAME_LENGTH) {
      setTooLong(true);
      add.reset();
      return;
    }
    setTooLong(false);
    add.mutate(name, {
      onSuccess: (player) => {
        setName("");
        onDone(t("players.add.added", { name: player.name }));
      },
    });
  }

  // The API refuses a removed player's name; the organizer restores them instead.
  const removedHolder =
    add.error instanceof ApiError &&
    errorCodeOf(add.error) === "player_name_taken" &&
    add.error.detail.removed === true &&
    typeof add.error.detail.player_id === "string" &&
    typeof add.error.detail.name === "string"
      ? { id: add.error.detail.player_id, name: add.error.detail.name }
      : undefined;
  const error =
    (tooLong
      ? t("auth.errors.nameTooLong", { count: MAX_NAME_LENGTH })
      : undefined) ??
    nameTaken(add.error) ??
    (errorCodeOf(add.error) === "player_limit_reached"
      ? t("players.errors.limit")
      : undefined) ??
    fieldErrors(t, add.error).name ??
    (add.isError ? t("players.errors.generic") : undefined);

  return (
    <form
      noValidate
      onSubmit={submit}
      aria-labelledby="add-player"
      className="space-y-3 rounded-lg border border-border-surface bg-card p-4 text-card-foreground"
    >
      <h2 id="add-player" className="font-display text-display-section">
        {t("players.add.heading")}
      </h2>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <FormField
          label={t("players.add.name")}
          name="name"
          autoComplete="off"
          required
          maxLength={MAX_NAME_LENGTH}
          value={name}
          error={error}
          className="flex-1"
          onChange={(event) => {
            setName(event.target.value);
            setTooLong(false);
          }}
        />
        <Button type="submit" className="sm:mt-7" disabled={add.isPending}>
          {add.isPending ? t("players.add.adding") : t("players.add.submit")}
        </Button>
      </div>
      {removedHolder !== undefined && (
        <Button
          type="button"
          variant="outline"
          disabled={restore.isPending}
          onClick={() => {
            onDone("");
            restore.mutate(
              { playerId: removedHolder.id, removed: false },
              {
                onSuccess: () => {
                  setName("");
                  add.reset();
                  onDone(
                    t("players.removed.restored", { name: removedHolder.name }),
                  );
                },
              },
            );
          }}
        >
          {t("players.removed.restoreLabel", { name: removedHolder.name })}
        </Button>
      )}
    </form>
  );
}

function PlayerRow({
  leagueId,
  player,
  onDone,
}: {
  leagueId: string;
  player: PlayerRead;
  onDone: (message: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const rename = useMutation(playerMutations.rename(queryClient, leagueId));
  const remove = useMutation(playerMutations.setRemoved(queryClient, leagueId));
  const nameTaken = useNameTaken();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(player.name);
  const [tooLong, setTooLong] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const list = new Intl.ListFormat(i18n.resolvedLanguage);
  // BR-002: asked when the dialog opens, so the block is explained before
  // the organizer confirms rather than after.
  const unfinished = useQuery(
    playerQueries.unfinishedTournaments(leagueId, player.id, confirming),
  );
  const blockedBy = unfinished.data ?? [];

  function stopEditing() {
    setEditing(false);
    setName(player.name);
    setTooLong(false);
    rename.reset();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      stopEditing();
    }
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    onDone("");
    remove.reset();
    if (name.trim().length > MAX_NAME_LENGTH) {
      setTooLong(true);
      rename.reset();
      return;
    }
    setTooLong(false);
    rename.mutate(
      { playerId: player.id, name },
      {
        onSuccess: (renamed) => {
          setEditing(false);
          onDone(t("players.rename.saved", { name: renamed.name }));
        },
      },
    );
  }

  const renameError =
    (tooLong
      ? t("auth.errors.nameTooLong", { count: MAX_NAME_LENGTH })
      : undefined) ??
    nameTaken(rename.error) ??
    fieldErrors(t, rename.error).name ??
    (rename.isError ? t("players.errors.generic") : undefined);
  const removeError = remove.isError
    ? ruleOf(remove.error) === "BR-002"
      ? t("players.remove.inTournament", { name: player.name })
      : t("players.errors.generic")
    : undefined;

  return (
    <li className="break-inside-avoid border-t border-border py-2 first:border-t-0">
      {editing ? (
        <form
          noValidate
          onSubmit={submit}
          className="flex flex-col gap-2 sm:flex-row sm:items-start"
        >
          <div className="flex-1 space-y-1">
            <Input
              aria-label={t("players.rename.name", { name: player.name })}
              aria-invalid={renameError === undefined ? undefined : true}
              aria-describedby={
                renameError === undefined ? undefined : `${player.id}-error`
              }
              // eslint-disable-next-line jsx-a11y-x/no-autofocus -- focus moves into the field the user asked to edit
              autoFocus
              autoComplete="off"
              maxLength={MAX_NAME_LENGTH}
              value={name}
              className="text-base"
              onKeyDown={onKeyDown}
              onChange={(event) => {
                setName(event.target.value);
                setTooLong(false);
              }}
            />
            {renameError !== undefined && (
              <p
                id={`${player.id}-error`}
                className="text-body-sm font-bold break-words text-destructive"
              >
                {renameError}
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              type="submit"
              className="flex-1 sm:flex-none"
              disabled={rename.isPending}
            >
              {t("players.rename.save")}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="flex-1 sm:flex-none"
              onClick={stopEditing}
            >
              {t("players.rename.cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex items-center justify-between gap-2">
          <span className="min-w-0 text-body-md font-bold break-words">
            {player.name}
          </span>
          <span className="flex shrink-0 gap-1">
            <Button
              type="button"
              variant="ghost"
              aria-label={t("players.rename.label", { name: player.name })}
              className="px-3"
              onClick={() => {
                onDone("");
                remove.reset();
                setName(player.name);
                setEditing(true);
              }}
            >
              {t("players.rename.action")}
            </Button>
            <AlertDialog open={confirming} onOpenChange={setConfirming}>
              <AlertDialogTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label={t("players.remove.label", { name: player.name })}
                  className="px-3 text-destructive"
                  disabled={remove.isPending}
                >
                  {t("players.remove.action")}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    {t("players.remove.title", { name: player.name })}
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    {blockedBy.length > 0
                      ? t("players.remove.blocked", {
                          name: player.name,
                          tournaments: list.format(
                            blockedBy.map((tournament) => tournament.name),
                          ),
                        })
                      : t("players.remove.body", { name: player.name })}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>
                    {t("players.remove.cancel")}
                  </AlertDialogCancel>
                  {blockedBy.length === 0 && (
                    <AlertDialogAction
                      className={buttonVariants({ variant: "destructive" })}
                      onClick={() => {
                        onDone("");
                        // mutateAsync, not mutate's callbacks: the reload drops
                        // this row before they would run, and the news is lost.
                        remove
                          .mutateAsync({ playerId: player.id, removed: true })
                          .then(
                            () => {
                              onDone(
                                t("players.remove.removed", {
                                  name: player.name,
                                }),
                              );
                            },
                            () => undefined, // shown by remove.error
                          );
                      }}
                    >
                      {t("players.remove.confirm")}
                    </AlertDialogAction>
                  )}
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </span>
        </div>
      )}
      {removeError !== undefined && (
        <p
          role="alert"
          className="text-body-sm font-bold break-words text-destructive"
        >
          {removeError}
        </p>
      )}
    </li>
  );
}

function RemovedRow({
  leagueId,
  player,
  onDone,
}: {
  leagueId: string;
  player: PlayerRead;
  onDone: (message: string) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const restore = useMutation(
    playerMutations.setRemoved(queryClient, leagueId),
  );

  return (
    <li className="flex items-center justify-between gap-2 border-t border-border py-2 first:border-t-0">
      <span className="min-w-0 text-body-md break-words text-muted-foreground">
        {player.name}
      </span>
      <Button
        type="button"
        variant="outline"
        aria-label={t("players.removed.restoreLabel", { name: player.name })}
        disabled={restore.isPending}
        onClick={() => {
          onDone("");
          // mutateAsync, not mutate's callbacks: the reload drops this row
          // before they would run, and the news is lost.
          restore.mutateAsync({ playerId: player.id, removed: false }).then(
            () => {
              onDone(t("players.removed.restored", { name: player.name }));
            },
            () => undefined,
          );
        }}
      >
        {t("players.removed.restore")}
      </Button>
    </li>
  );
}
