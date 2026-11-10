import { useTranslation } from "react-i18next";

import type { SeasonRead } from "@/demo/contract";

/** A season's name: its own, or "Season 2" in the UI language (FR-020). */
export function useSeasonName(): (season: SeasonRead) => string {
  const { t } = useTranslation();
  return (season) =>
    season.name ?? t("shell.seasonName", { number: season.number });
}
