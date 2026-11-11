import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type SubmitEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { errorCodeOf } from "@/features/auth/apiErrors";
import { FormField } from "@/features/auth/FormField";
import { MIN_PASSWORD_LENGTH } from "@/features/auth/passwordRules";

import { adminMutations } from "./api";
import { CopyButton } from "./CopyButton";
import { lengthOf, MAX_PASSWORD_LENGTH } from "./limits";

interface ResetPasswordDialogProps {
  userId: string;
  name: string;
}

type Mode = "generate" | "choose";

/**
 * Resets an account's password (FR-006, ADR-006). The dialog is the
 * confirmation: it says what the reset does, then asks for the button. A
 * generated password is shown once, in the dialog's second step, and is
 * gone when the dialog closes.
 */
export function ResetPasswordDialog({
  userId,
  name,
}: ResetPasswordDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const reset = useMutation(adminMutations.resetPassword(queryClient));
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("generate");
  const [local, setLocal] = useState<string>();
  const groupId = useId();

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    let temporaryPassword: string | null = null;
    if (mode === "choose") {
      const value = new FormData(event.currentTarget).get("temporaryPassword");
      temporaryPassword = typeof value === "string" ? value : "";
      const length = lengthOf(temporaryPassword);
      if (length < MIN_PASSWORD_LENGTH || length > MAX_PASSWORD_LENGTH) {
        setLocal(
          length === 0
            ? t("admin.reset.required")
            : length < MIN_PASSWORD_LENGTH
              ? t("admin.reset.tooShort", { count: MIN_PASSWORD_LENGTH })
              : t("admin.reset.tooLong", { count: MAX_PASSWORD_LENGTH }),
        );
        reset.reset();
        return;
      }
    }
    setLocal(undefined);
    reset.mutate({ userId, temporaryPassword });
  }

  const code = errorCodeOf(reset.error);
  const serverField =
    code === "validation_failed"
      ? t("admin.reset.tooShort", { count: MIN_PASSWORD_LENGTH })
      : undefined;
  const errorText =
    code === "user_not_found"
      ? t("admin.reset.notFound")
      : reset.isError && serverField === undefined
        ? t("admin.reset.failed")
        : undefined;
  const generated = reset.data?.temporary_password ?? null;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          // The generated password leaves the page with the dialog.
          reset.reset();
          setMode("generate");
          setLocal(undefined);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          aria-label={t("admin.organizers.resetFor", { name })}
          className="w-full sm:w-auto"
        >
          {t("admin.organizers.reset")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        {reset.isSuccess ? (
          <div className="space-y-4">
            <DialogHeader>
              <DialogTitle>{t("admin.reset.doneTitle")}</DialogTitle>
              <DialogDescription>
                {generated === null
                  ? t("admin.reset.doneChosen", { name })
                  : t("admin.reset.doneGenerated", { name })}
              </DialogDescription>
            </DialogHeader>
            {generated !== null && (
              <div className="space-y-2">
                <p
                  data-testid="temporary-password"
                  className="rounded-lg border border-border-surface bg-background px-4 py-3 font-mono text-body-lg font-bold break-all select-all"
                >
                  {generated}
                </p>
                <CopyButton
                  text={generated}
                  label={t("admin.reset.copy")}
                  copied={t("admin.reset.copied")}
                  failed={t("admin.reset.copyFailed")}
                />
              </div>
            )}
            <DialogFooter>
              <Button
                type="button"
                size="lg"
                onClick={() => {
                  setOpen(false);
                  reset.reset();
                }}
              >
                {t("admin.reset.done")}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form noValidate onSubmit={submit} className="space-y-4">
            <DialogHeader>
              <DialogTitle>{t("admin.reset.title", { name })}</DialogTitle>
              <DialogDescription>
                {t("admin.reset.description", { name })}
              </DialogDescription>
            </DialogHeader>
            <fieldset className="space-y-1">
              <legend className="sr-only">{t("admin.reset.modes")}</legend>
              {(["generate", "choose"] as const).map((option) => (
                <div key={option} className="flex min-h-11 items-center gap-3">
                  {/* Native: Radix's radio group needs ResizeObserver inside a form. */}
                  <input
                    id={`${groupId}-${option}`}
                    type="radio"
                    name="mode"
                    checked={mode === option}
                    className="size-6 shrink-0 accent-primary"
                    onChange={() => {
                      setMode(option);
                      setLocal(undefined);
                    }}
                  />
                  <Label
                    htmlFor={`${groupId}-${option}`}
                    className="text-body-md font-normal"
                  >
                    {t(`admin.reset.${option}`)}
                  </Label>
                </div>
              ))}
            </fieldset>
            {mode === "choose" && (
              <FormField
                label={t("admin.reset.temporary")}
                name="temporaryPassword"
                autoComplete="off"
                spellCheck={false}
                required
                hint={t("admin.reset.hint", { count: MIN_PASSWORD_LENGTH })}
                error={local ?? serverField}
              />
            )}
            <p role="alert" className="text-body-md font-bold text-destructive">
              {errorText}
            </p>
            <DialogFooter className="gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setOpen(false);
                }}
              >
                {t("admin.reset.cancel")}
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={reset.isPending}
              >
                {reset.isPending
                  ? t("admin.reset.working")
                  : t("admin.reset.confirm")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
