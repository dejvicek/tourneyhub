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
    // The same names as the bracket's (finals.matchTitle), on every screen.
    if (info.match.kind === "third_place") {
      return t("finals.matchTitle.third_place");
    }
    const name = (["final", "semifinal", "quarterfinal"] as const)[fromEnd - 1];
    return t(`finals.matchTitle.${name ?? "round_of_16"}`, {
      n: info.match.position,
    });
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
