import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type SubmitEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";
import { isDemoMode } from "@/lib/demoMode";
import { paths } from "@/lib/paths";

import { authMutations, authQueries } from "./api";
import { errorCodeOf, retryAfterOf } from "./apiErrors";
import { AuthLayout } from "./AuthLayout";
import { FormField } from "./FormField";
import { safeNext } from "./loginPath";
import { ShowPasswords } from "./ShowPasswords";
import { useWaitUntil } from "./useWaitUntil";

/** The shape P2b's email pattern checks: something, an @, something. */
const EMAIL = /^[^\s@]+@[^\s@]+$/;

/** Login with email and password (FR-003); returns to where the guard stopped. */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const logIn = useMutation(authMutations.logIn(queryClient));
  const wait = useWaitUntil();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [local, setLocal] = useState<{ email?: string; password?: string }>({});

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    // An empty field or an address without an @ is never worth a request,
    // which would count toward the throttle (P2a).
    const problems = {
      email: EMAIL.test(email.trim())
        ? undefined
        : t("auth.errors.emailInvalid"),
      password: password === "" ? t("auth.errors.passwordRequired") : undefined,
    };
    setLocal(problems);
    if (problems.email !== undefined || problems.password !== undefined) {
      logIn.reset();
      return;
    }
    logIn.mutate(
      { email, password },
      {
        onSuccess: () => {
          void queryClient.query(authQueries.me()).then((me) =>
            // ADR-006: a password set by the admin is changed first.
            navigate(
              me.must_change_password
                ? paths.changePassword
                : safeNext(searchParams.get("next")),
              { replace: true },
            ),
          );
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

  const code = errorCodeOf(logIn.error);
  const waiting = wait.remaining > 0;
  const message = waiting
    ? t("auth.errors.wait", { count: wait.remaining })
    : logIn.isError && code !== "too_many_attempts"
      ? code === "not_authenticated"
        ? t("auth.login.wrong")
        : t("auth.errors.generic")
      : undefined;

  return (
    <AuthLayout title={t("auth.login.title")} lead={t("auth.login.lead")}>
      <DocumentTitle screen={t("auth.login.title")} />
      {isDemoMode(import.meta.env) && (
        <DemoAccount
          onFill={(account) => {
            setEmail(account.email);
            setPassword(account.password);
          }}
        />
      )}
      <form noValidate onSubmit={submit} className="space-y-4">
        <FormField
          label={t("auth.login.email")}
          type="email"
          name="email"
          autoComplete="username"
          required
          maxLength={320}
          error={local.email}
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
          }}
        />
        <FormField
          label={t("auth.login.password")}
          type={show ? "text" : "password"}
          name="password"
          autoComplete="current-password"
          required
          maxLength={1024}
          error={local.password}
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
          }}
        />
        <ShowPasswords checked={show} onChange={setShow} />
        <p role="alert" className="text-body-md font-bold text-destructive">
          {message}
        </p>
        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={logIn.isPending || waiting}
        >
          {waiting
            ? t("auth.errors.waitButton", { count: wait.remaining })
            : logIn.isPending
              ? t("auth.login.submitting")
              : t("auth.login.submit")}
        </Button>
      </form>
      <p className="text-body-md">
        {t("auth.login.noAccount")}{" "}
        <Link
          to={paths.signUp}
          className="inline-flex min-h-11 items-center font-bold text-primary underline underline-offset-4"
        >
          {t("auth.login.signUp")}
        </Link>
      </p>
    </AuthLayout>
  );
}

/** Demo mode only: the seeded account, from the demo's fake API. */
function DemoAccount({
  onFill,
}: {
  onFill: (account: { email: string; password: string }) => void;
}) {
  const { t } = useTranslation();
  const account = useQuery(authQueries.demoAccount());

  if (account.data === undefined) {
    return null;
  }
  const { email, password } = account.data;
  return (
    <section
      aria-labelledby="demo-account"
      className="space-y-2 rounded-lg bg-notice-info px-4 py-3.5 text-notice-info-foreground"
    >
      <h2 id="demo-account" className="text-body-md font-bold">
        {t("auth.login.demoTitle")}
      </h2>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-body-sm">
        <dt className="font-bold">{t("auth.login.email")}</dt>
        <dd className="min-w-0 break-words">{email}</dd>
        <dt className="font-bold">{t("auth.login.password")}</dt>
        <dd className="min-w-0 break-words">{password}</dd>
      </dl>
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          onFill({ email, password });
        }}
      >
        {t("auth.login.demoFill")}
      </Button>
    </section>
  );
}
