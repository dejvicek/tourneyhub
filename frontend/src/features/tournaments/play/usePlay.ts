import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { playQueries } from "@/features/fields/api";
import { tournamentQueries } from "@/features/tournaments/api";

import { buildModel } from "./model";

/** The running tournament as the play screens read it (screens 6–8). */
export function usePlay(leagueId: string, tournamentId: string) {
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const players = useQuery(playQueries.players(leagueId));
  const play = useQuery(playQueries.view(leagueId, tournamentId));

  const model = useMemo(
    () =>
      tournament.data && players.data
        ? buildModel(tournament.data, players.data, play.data)
        : undefined,
    [tournament.data, players.data, play.data],
  );
  return {
    model,
    play: play.data,
    failed: tournament.isError || players.isError || play.isError,
  };
}
