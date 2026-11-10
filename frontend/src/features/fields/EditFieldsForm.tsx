import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

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
import type { FieldRead } from "@/demo/contract";
import { fieldMutations } from "@/features/fields/api";
import { FieldBadge } from "@/features/tournaments/play/FieldBadge";
import { PlusIcon } from "@/features/tournaments/play/icons";
import type { PlayModel } from "@/features/tournaments/play/model";
import { Notice } from "@/features/tournaments/play/Notice";
import { useNames } from "@/features/tournaments/play/useNames";

import { useFieldError } from "./useFieldError";

/** The number the next field gets, the lowest free one; the request carries it (BR-132, ADR-008). */
function nextNumber(fields: readonly FieldRead[]): number {
  const taken = new Set(fields.map((field) => field.number));
  let number = 1;
  while (taken.has(number)) {
    number += 1;
  }
  return number;
}

interface EditFieldsFormProps {
  leagueId: string;
  model: PlayModel;
  onDone: () => void;
}

/** Screen 6d: add or remove fields while the tournament runs (FR-090, BR-132). */
export function EditFieldsForm({
  leagueId,
  model,
  onDone,
}: EditFieldsFormProps) {
  const { t } = useTranslation();
  const names = useNames(model);
  const tournamentId = model.tournament.id;
  const add = useMutation(fieldMutations.add(leagueId, tournamentId));
  const remove = useMutation(fieldMutations.remove(leagueId, tournamentId));
  const errorText = useFieldError(add.error ?? remove.error);
  const [removing, setRemoving] = useState<FieldRead | null>(null);
  const [status, setStatus] = useState("");
  const next = nextNumber(model.fields);
  const last = model.fields.length === 1;
  const removingMatch =
    removing?.match_id == null
      ? undefined
      : model.matches.get(removing.match_id);

  return (
    <div className="space-y-4">
      <ul className="space-y-2">
        {model.fields.map((field) => {
          const info =
            field.match_id === null
              ? undefined
              : model.matches.get(field.match_id);
          return (
            <li
              key={field.id}
              className="flex items-center gap-3 rounded-lg border border-border-surface bg-card p-3 text-card-foreground"
            >
              <FieldBadge number={field.number} free={info === undefined} />
              <span className="min-w-0 flex-1 text-body-sm">
                {info ? names.match(info.match.sides) : t("fields.card.free")}
              </span>
              <Button
                type="button"
                variant="outline"
                className="h-11"
                disabled={last || remove.isPending}
                aria-label={t("fields.edit.removeField", {
                  number: field.number,
                })}
                onClick={() => {
                  setRemoving(field);
                }}
              >
                {t("fields.edit.remove")}
              </Button>
            </li>
          );
        })}
      </ul>
      {last && (
        <p className="text-body-sm text-muted-foreground">
          {t("fields.edit.lastField")}
        </p>
      )}
      <button
        type="button"
        disabled={add.isPending}
        onClick={() => {
          add.mutate(next, {
            onSuccess: (field) => {
              setStatus(t("fields.edit.added", { number: field.number }));
            },
          });
        }}
        className="flex min-h-11 w-full items-start gap-3 rounded-lg border-2 border-dashed border-input p-4 text-left outline-hidden hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-50"
      >
        <PlusIcon className="mt-0.5 size-6 shrink-0" />
        <span className="space-y-1">
          <span className="block text-body-md font-bold">
            {t("fields.edit.add")}
          </span>
          <span className="block text-body-sm text-muted-foreground">
            {t("fields.edit.addHint", { number: next })}
          </span>
        </span>
      </button>
      <Notice variant="info" title={t("fields.edit.noticeTitle")}>
        {t("fields.edit.noticeBody")}
      </Notice>
      <p role="status" className="text-body-sm">
        {status}
      </p>
      {errorText !== null && (
        <p role="alert" className="text-body-sm font-bold text-destructive">
          {errorText}
        </p>
      )}
      <Button
        type="button"
        className="h-14 w-full rounded-lg text-button-lg"
        onClick={onDone}
      >
        {/* TODO(foundation-buttons): size lg after the rebase. */}
        {t("fields.edit.done")}
      </Button>

      {/* The "Remove field" confirm the design lacks (FR-090, BR-132). */}
      <AlertDialog
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRemoving(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("fields.edit.confirmTitle", { number: removing?.number ?? 0 })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {removingMatch
                ? t("fields.edit.confirmBusy", {
                    match: names.match(removingMatch.match.sides),
                  })
                : t("fields.edit.confirmFree")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("fields.edit.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (removing) {
                  const number = removing.number;
                  remove.mutate(removing.id, {
                    onSuccess: () => {
                      setStatus(t("fields.edit.removed", { number }));
                    },
                  });
                }
              }}
            >
              {t("fields.edit.confirmAction", {
                number: removing?.number ?? 0,
              })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
