import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ResponsiveSheet } from "@/components/ResponsiveSheet";

interface PlaceholderSheetProps {
  title: string;
  /** The screen's number in the Figma file, e.g. "6c". */
  screen: string;
  children?: ReactNode;
}

/**
 * An overlay not built yet: its title, its design screen and a note. It
 * renders no <title>; the screen under it keeps its own.
 */
export function PlaceholderSheet({
  title,
  screen,
  children,
}: PlaceholderSheetProps) {
  const { t } = useTranslation();

  return (
    <ResponsiveSheet
      title={title}
      description={t("placeholder.screen", { screen })}
    >
      <p className="text-body-md text-muted-foreground">
        {t("placeholder.body")}
      </p>
      {children}
    </ResponsiveSheet>
  );
}
