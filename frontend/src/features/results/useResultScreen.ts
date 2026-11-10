import { useTranslation } from "react-i18next";

import type { MatchInfo, PlayModel } from "@/features/tournaments/play/model";
import { usePlay } from "@/features/tournaments/play/usePlay";
import { useRouteParam } from "@/hooks/useRouteParam";

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

/** The result overlay's data. */
export function useResultScreen() {
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const matchId = useRouteParam("matchId");
  const play = usePlay(leagueId, tournamentId);
  return { ...play, leagueId, tournamentId, matchId };
}
