import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type SubmitEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";
import { isLanguage } from "@/i18n/language";
import { paths } from "@/lib/paths";

import { authMutations } from "./api";
import { errorCodeOf, retryAfterOf } from "./apiErrors";
import { AuthLayout } from "./AuthLayout";
import { fieldErrors } from "./fieldErrors";
import { FormField } from "./FormField";
import { MIN_PASSWORD_LENGTH } from "./passwordRules";
import { ShowPasswords } from "./ShowPasswords";
import { useWaitUntil } from "./useWaitUntil";

type Field = "signupCode" | "email" | "displayName" | "password";

/** Sign-up with the instance's code (FR-001, FR-002); logs in as a login does. */
export function SignUpPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const signUp = useMutation(authMutations.signUp(queryClient));
  const wait = useWaitUntil();
  const [show, setShow] = useState(false);
  const [local, setLocal] = useState<Partial<Record<Field, string>>>({});

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const text = (name: string) => {
      const value = form.get(name);
      return typeof value === "string" ? value : "";
    };
    // Every field is required: an empty form marks all four at once, without
    // a request that would count toward the throttle (P2b).
    const empty: Partial<Record<Field, string>> = {
      ...(text("signupCode").trim() === ""
        ? { signupCode: t("auth.errors.codeRequired") }
        : {}),
      ...(text("email").trim() === ""
        ? { email: t("auth.errors.emailInvalid") }
        : {}),
      ...(text("displayName").trim() === ""
        ? { displayName: t("auth.errors.nameRequired") }
        : {}),
      ...(text("password") === ""
        ? {
            password: t("auth.errors.tooShort", { count: MIN_PASSWORD_LENGTH }),
          }
        : {}),
    };
    setLocal(empty);
    if (Object.keys(empty).length > 0) {
      signUp.reset();
      return;
    }
    signUp.mutate(
      {
        signupCode: text("signupCode"),
        email: text("email"),
        displayName: text("displayName"),
        password: text("password"),
        // FR-081: the language of this screen is the account's.
        language: isLanguage(i18n.resolvedLanguage)
          ? i18n.resolvedLanguage
          : "en",
      },
      {
        onSuccess: () => {
          void navigate(paths.myLeagues, { replace: true });
        },
        onError: (error) => {
          const seconds = retryAfterOf(error);
          if (seconds !== undefined) {
            wait.start(seconds);
          }
        },
      },
    );
  }

  const code = errorCodeOf(signUp.error);
  const fields = fieldErrors(t, signUp.error);
  const codeError =
    local.signupCode ??
    (code === "invalid_signup_code"
      ? t("auth.errors.invalidSignupCode")
      : undefined);
  const emailError =
    local.email ??
    (code === "email_taken" ? t("auth.errors.emailTaken") : fields.email);
  const waiting = wait.remaining > 0;
  const message = waiting
    ? t("auth.errors.wait", { count: wait.remaining })
    : signUp.isError &&
        code !== "too_many_attempts" &&
        code !== "invalid_signup_code" &&
        code !== "email_taken" &&
        code !== "validation_failed"
      ? t("auth.errors.generic")
      : undefined;

  return (
    <AuthLayout title={t("auth.signUp.title")} lead={t("auth.signUp.lead")}>
      <DocumentTitle screen={t("auth.signUp.title")} />
      <form noValidate onSubmit={submit} className="space-y-4">
        <FormField
          label={t("auth.signUp.code")}
          name="signupCode"
          autoComplete="off"
          required
          maxLength={256}
          error={codeError}
        />
        <FormField
          label={t("auth.signUp.email")}
          type="email"
          name="email"
          autoComplete="email"
          required
          maxLength={320}
          error={emailError}
        />
        <FormField
          label={t("auth.signUp.displayName")}
          name="displayName"
          autoComplete="name"
          required
          maxLength={100}
          hint={t("auth.signUp.displayNameHint")}
          error={local.displayName ?? fields.display_name}
        />
        <FormField
          label={t("auth.signUp.password")}
          type={show ? "text" : "password"}
          name="password"
          autoComplete="new-password"
          required
          maxLength={1024}
          hint={t("auth.password.rule", { count: MIN_PASSWORD_LENGTH })}
          error={local.password ?? fields.password}
        />
        <ShowPasswords checked={show} onChange={setShow} />
        <p role="alert" className="text-body-md font-bold text-destructive">
          {message}
        </p>
        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={signUp.isPending || waiting}
        >
          {waiting
            ? t("auth.errors.waitButton", { count: wait.remaining })
            : signUp.isPending
              ? t("auth.signUp.submitting")
              : t("auth.signUp.submit")}
        </Button>
      </form>
      <p className="text-body-md">
        {t("auth.signUp.haveAccount")}{" "}
        <Link
          to={paths.login}
          className="inline-flex min-h-11 items-center font-bold text-primary underline underline-offset-4"
        >
          {t("auth.signUp.logIn")}
        </Link>
      </p>
    </AuthLayout>
  );
}
