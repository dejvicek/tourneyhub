import { useTranslation } from "react-i18next";
import { generatePath, useSearchParams } from "react-router";

import type { MatchInfo, PlayModel } from "@/features/tournaments/play/model";
import { usePlay } from "@/features/tournaments/play/usePlay";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

/** "Round 4", "Semifinal 1", "Final": the match's name in its phase. */
export function useMatchTitle() {
  const { t } = useTranslation();
  return (model: PlayModel, info: MatchInfo): string => {
    if (info.phase.kind === "group") {
      return t("roundRobin.round", { number: info.round.round_no });
    }
    const rounds = model.tournament.rounds
      .filter((round) => round.phase_id === info.phase.id)
      .sort((a, b) => a.round_no - b.round_no);
    const fromEnd =
      rounds.length - rounds.findIndex((r) => r.id === info.round.id);
    if (info.match.kind === "third_place") {
      return t("results.titles.thirdPlace");
    }
    switch (fromEnd) {
      case 1:
        return t("results.titles.final");
      case 2:
        return t("results.titles.semifinal", { number: info.match.position });
      case 3:
        return t("results.titles.quarterfinal", {
          number: info.match.position,
        });
      default:
        return t("results.titles.knockoutRound", {
          round: info.round.round_no,
          number: info.match.position,
        });
    }
  };
}

/** The result screen's data and where it goes back to. */
export function useResultScreen() {
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const matchId = useRouteParam("matchId");
  const [search] = useSearchParams();
  const play = usePlay(leagueId, tournamentId);
  const params = { leagueId, tournamentId };
  // TODO(foundation-routes): the overlay's parent route decides this.
  const backTo =
    search.get("from") === "fields"
      ? generatePath(paths.fields, params)
      : generatePath(paths.tournament, params);
  return { ...play, leagueId, tournamentId, matchId, backTo };
}
