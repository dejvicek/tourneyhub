import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";

type TournamentType = components["schemas"]["TournamentType"];

/** "6 pairs" or "6 players", by what the tournament's entries are. */
export function useEntryCount() {
  const { t } = useTranslation();
  return (type: TournamentType, count: number): string => {
    switch (type) {
      case "singles":
      case "monster_dyp":
        return t("roundRobin.entries.players", { count });
      case "doubles":
      case "dyp":
        return t("roundRobin.entries.pairs", { count });
    }
  };
}
