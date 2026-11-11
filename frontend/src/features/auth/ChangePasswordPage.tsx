import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type SubmitEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";
import { paths } from "@/lib/paths";

import { authMutations, authQueries } from "./api";
import { errorCodeOf } from "./apiErrors";
import { AuthLayout } from "./AuthLayout";
import { fieldErrors } from "./fieldErrors";
import { FormField } from "./FormField";
import { MIN_PASSWORD_LENGTH } from "./passwordRules";
import { ShowPasswords } from "./ShowPasswords";

/**
 * The password change (FR-004): the current password and a new one. ADR-006:
 * it logs out the other devices, and it is the one screen that works while
 * the account must change its password.
 */
export function ChangePasswordPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const me = useQuery(authQueries.me());
  const change = useMutation(authMutations.changePassword());
  const [show, setShow] = useState(false);
  const [formKey, setFormKey] = useState(0);
  const [local, setLocal] = useState<{ current?: string; new?: string }>({});

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const text = (name: string) => {
      const value = form.get(name);
      return typeof value === "string" ? value : "";
    };
    const currentPassword = text("currentPassword");
    const newPassword = text("newPassword");
    // An empty current password is caught here, together with a new one that
    // is too short, so both fields say what is wrong at once.
    if (currentPassword === "") {
      setLocal({
        current: t("auth.errors.currentRequired"),
        new:
          newPassword.length < MIN_PASSWORD_LENGTH
            ? t("auth.errors.tooShort", { count: MIN_PASSWORD_LENGTH })
            : undefined,
      });
      change.reset();
      return;
    }
    setLocal({});
    change.mutate(
      {
        currentPassword,
        newPassword,
      },
      {
        onSuccess: () => {
          // Empty fields: the passwords leave the page.
          setFormKey((key) => key + 1);
          void queryClient.invalidateQueries({
            queryKey: authQueries.me().queryKey,
          });
        },
      },
    );
  }

  const code = errorCodeOf(change.error);
  const fields = fieldErrors(t, change.error);
  const currentError =
    local.current ??
    (code === "wrong_password" ? t("auth.errors.wrongPassword") : undefined);
  const newError =
    local.new ??
    (code === "password_unchanged"
      ? t("auth.errors.passwordUnchanged")
      : fields.new_password);
  const failed =
    change.isError &&
    code !== "wrong_password" &&
    code !== "password_unchanged" &&
    code !== "validation_failed";

  return (
    <AuthLayout
      title={t("auth.changePassword.title")}
      lead={t("auth.changePassword.lead")}
    >
      <DocumentTitle screen={t("auth.changePassword.title")} />
      {me.data?.must_change_password === true && (
        <p className="rounded-lg bg-notice-warning px-4 py-3.5 text-body-md text-notice-warning-foreground">
          {t("auth.changePassword.required")}
        </p>
      )}
      <form key={formKey} noValidate onSubmit={submit} className="space-y-4">
        <FormField
          label={t("auth.changePassword.current")}
          type={show ? "text" : "password"}
          name="currentPassword"
          autoComplete="current-password"
          required
          maxLength={1024}
          error={currentError}
        />
        <FormField
          label={t("auth.changePassword.new")}
          type={show ? "text" : "password"}
          name="newPassword"
          autoComplete="new-password"
          required
          maxLength={1024}
          hint={t("auth.password.rule", { count: MIN_PASSWORD_LENGTH })}
          error={newError}
        />
        <ShowPasswords checked={show} onChange={setShow} />
        <p role="alert" className="text-body-md font-bold text-destructive">
          {failed ? t("auth.errors.generic") : undefined}
        </p>
        <p role="status" className="text-body-md font-bold text-primary">
          {change.isSuccess ? t("auth.changePassword.done") : undefined}
        </p>
        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={change.isPending}
        >
          {change.isPending
            ? t("auth.changePassword.submitting")
            : t("auth.changePassword.submit")}
        </Button>
      </form>
      {me.data?.must_change_password !== true && (
        <Link
          to={paths.myLeagues}
          className="inline-flex min-h-11 items-center text-body-md font-bold text-primary underline underline-offset-4"
        >
          {t("auth.account.myLeagues")}
        </Link>
      )}
    </AuthLayout>
  );
}
