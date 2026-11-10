import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { PlaceholderSheet } from "@/components/PlaceholderSheet";
import { BestOfResultPage } from "@/features/results/BestOfResultPage";
import { matchFormat } from "@/features/results/matchFormat";
import { tournamentQueries } from "@/features/tournaments/api";
import { useRouteParam } from "@/hooks/useRouteParam";

// Placeholder (FR-050–FR-053, FR-082), an overlay over the screen that
// opened it. A match of one game gets the simple form (7), a best-of match
// the form for several games (7b).
export function EnterResultPage() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const matchId = useRouteParam("matchId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));

  if (tournament.data === undefined) {
    return null;
  }
  const format = matchFormat(tournament.data, matchId);
  if (format !== undefined && format !== "bo1") {
    return <BestOfResultPage />;
  }
  return <PlaceholderSheet screen="7" title={t("results.enter.title")} />;
}
