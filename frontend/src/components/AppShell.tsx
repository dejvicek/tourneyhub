import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, Outlet } from "react-router";

import { DemoNotice } from "@/components/DemoNotice";
import { LanguageSwitch } from "@/components/LanguageSwitch";

/**
 * The shell of the pages outside a league: home, login, my leagues, share
 * links. `account` is the signed-in user's menu, which the route table
 * passes in; it sits next to the language switch.
 */
export function AppShell({ account }: { account?: ReactNode }) {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b bg-nav">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="font-display text-display-section">
            {t("app.name")}
          </Link>
          <div className="flex shrink-0 items-center gap-2">
            <LanguageSwitch />
            {account}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 space-y-6 px-4 py-6">
        <DemoNotice />
        <Outlet />
      </main>
    </div>
  );
}
