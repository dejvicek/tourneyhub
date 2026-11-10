import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { DocumentTitle } from "@/components/DocumentTitle";

interface PlaceholderPageProps {
  title: string;
  /** The screen's number in the Figma file, e.g. "6b"; none for screens outside it. */
  screen?: string;
  children?: ReactNode;
}

/** A screen not built yet: its title, its design screen and a note. */
export function PlaceholderPage({
  title,
  screen,
  children,
}: PlaceholderPageProps) {
  const { t } = useTranslation();

  return (
    <section className="space-y-4">
      <DocumentTitle screen={title} />
      {screen !== undefined && (
        <p className="text-caption font-bold text-muted-foreground">
          {t("placeholder.screen", { screen })}
        </p>
      )}
      <h1 className="font-display text-display-screen">{title}</h1>
      <p className="text-body-md text-muted-foreground">
        {t("placeholder.body")}
      </p>
      {children}
    </section>
  );
}
