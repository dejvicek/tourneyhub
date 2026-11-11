import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type SubmitEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { PageFallback } from "@/components/PageFallback";
import { Button } from "@/components/ui/button";
import { errorCodeOf } from "@/features/auth/apiErrors";
import { FormField } from "@/features/auth/FormField";
import { SettingsSection } from "@/features/leagues/SettingsSection";
import { i18n } from "@/i18n";

import { adminMutations, adminQueries } from "./api";
import { CopyButton } from "./CopyButton";
import {
  lengthOf,
  SIGNUP_CODE_MAX_LENGTH,
  SIGNUP_CODE_MIN_LENGTH,
} from "./limits";

type Done = "saved" | "generated" | "closed";

/**
 * The instance's sign-up code (FR-005, ADR-007): the admin sees it, sets or
 * generates a new one, or closes sign-up. Changing it leaves existing
 * accounts alone.
 */
export function SignupCodeSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const code = useQuery(adminQueries.signupCode());
  const save = useMutation(adminMutations.setSignupCode(queryClient));
  const generate = useMutation(adminMutations.generateSignupCode(queryClient));
  const [done, setDone] = useState<Done | null>(null);
  const [local, setLocal] = useState<string>();
  const [formKey, setFormKey] = useState(0);

  const busy = save.isPending || generate.isPending;
  const current = code.data?.signup_code ?? null;

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("signupCode");
    const next = (typeof value === "string" ? value : "").trim();
    const length = lengthOf(next);
    setDone(null);
    generate.reset();
    if (length < SIGNUP_CODE_MIN_LENGTH) {
      setLocal(
        length === 0
          ? t("admin.code.required")
          : t("admin.code.tooShort", { count: SIGNUP_CODE_MIN_LENGTH }),
      );
      save.reset();
      return;
    }
    if (length > SIGNUP_CODE_MAX_LENGTH) {
      setLocal(t("admin.code.tooLong", { count: SIGNUP_CODE_MAX_LENGTH }));
      save.reset();
      return;
    }
    setLocal(undefined);
    save.mutate(next, {
      onSuccess: () => {
        setDone("saved");
        setFormKey((key) => key + 1); // an empty field: the code is shown above
      },
    });
  }

  const failure = save.error ?? generate.error;
  const serverField =
    errorCodeOf(save.error) === "validation_failed"
      ? t("admin.code.tooShort", { count: SIGNUP_CODE_MIN_LENGTH })
      : undefined;
  const failed = failure !== null && serverField === undefined;

  return (
    <SettingsSection
      id="signup-code"
      title={t("admin.code.heading")}
      description={t("admin.code.lead")}
    >
      {code.isPending ? (
        <PageFallback />
      ) : code.isError ? (
        <div role="alert" className="space-y-3">
          <p className="text-body-md">{t("admin.loadFailed")}</p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void code.refetch();
            }}
          >
            {t("admin.retry")}
          </Button>
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {current === null ? (
              <p className="rounded-lg bg-notice-warning px-4 py-3.5 text-body-md text-notice-warning-foreground">
                {t("admin.code.closed")}
              </p>
            ) : (
              <>
                <p className="text-body-sm font-bold text-muted-foreground">
                  {t("admin.code.current")}
                </p>
                <p
                  data-testid="signup-code"
                  className="rounded-lg border border-border-surface bg-background px-4 py-3 font-mono text-body-lg font-bold break-all select-all"
                >
                  {current}
                </p>
                <CopyButton
                  text={current}
                  label={t("admin.code.copy")}
                  copied={t("admin.code.copied")}
                  failed={t("admin.code.copyFailed")}
                />
              </>
            )}
            {code.data.updated_at !== null && (
              <p className="text-caption text-muted-foreground">
                {t("admin.code.changed", {
                  when: new Intl.DateTimeFormat(i18n.resolvedLanguage, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(code.data.updated_at)),
                })}
              </p>
            )}
          </div>
          <form
            key={formKey}
            noValidate
            onSubmit={submit}
            className="space-y-4"
          >
            <FormField
              label={t("admin.code.label")}
              name="signupCode"
              autoComplete="off"
              spellCheck={false}
              required
              hint={t("admin.code.hint", {
                min: SIGNUP_CODE_MIN_LENGTH,
                max: SIGNUP_CODE_MAX_LENGTH,
              })}
              error={local ?? serverField}
            />
            <Button type="submit" size="lg" className="w-full" disabled={busy}>
              {save.isPending ? t("admin.code.saving") : t("admin.code.save")}
            </Button>
          </form>
          <div className="flex flex-col gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setDone(null);
                setLocal(undefined);
                save.reset();
                generate.mutate(undefined, {
                  onSuccess: () => {
                    setDone("generated");
                  },
                });
              }}
            >
              {generate.isPending
                ? t("admin.code.generating")
                : t("admin.code.generate")}
            </Button>
            {current !== null && (
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setDone(null);
                  setLocal(undefined);
                  generate.reset();
                  save.mutate(null, {
                    onSuccess: () => {
                      setDone("closed");
                    },
                  });
                }}
              >
                {t("admin.code.close")}
              </Button>
            )}
          </div>
          <p role="alert" className="text-body-md font-bold text-destructive">
            {failed ? t("admin.code.failed") : undefined}
          </p>
          <p role="status" className="text-body-md font-bold text-primary">
            {done === "saved" && t("admin.code.saved")}
            {done === "generated" && t("admin.code.generated")}
            {done === "closed" && t("admin.code.closedDone")}
          </p>
        </>
      )}
    </SettingsSection>
  );
}
