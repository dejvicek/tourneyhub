import { useTranslation } from "react-i18next";
import { Link, Outlet } from "react-router";

import { LanguageSwitch } from "@/components/LanguageSwitch";

export function AppShell() {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            {t("app.name")}
          </Link>
          <LanguageSwitch />
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
