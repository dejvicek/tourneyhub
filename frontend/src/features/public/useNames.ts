import { useTranslation } from "react-i18next";

import type { PublicMatch, PublicPlayer, PublicTournament } from "./api";

/**
 * Names for players, entries and match sides, from the league's player list:
 * a rename shows everywhere (FR-012). A pair reads "A & B".
 */
export function useNames(
  players: PublicPlayer[],
  tournament?: PublicTournament,
) {
  const { t } = useTranslation();
  const byId = new Map(players.map((player) => [player.id, player.name]));
  const entries = new Map(
    (tournament?.entries ?? []).map((entry) => [entry.id, entry.player_ids]),
  );

  const ofPlayers = (ids: string[]): string => {
    const names = ids.map((id) => byId.get(id) ?? "?");
    const [a, b] = names;
    return b === undefined ? (a ?? "?") : t("publicView.match.pair", { a, b });
  };

  return {
    ofPlayers,
    ofEntry: (entryId: string) => ofPlayers(entries.get(entryId) ?? []),
    ofMatch: (match: PublicMatch) =>
      t("publicView.match.versus", {
        a: ofPlayers(match.sides[0]?.player_ids ?? []),
        b: ofPlayers(match.sides[1]?.player_ids ?? []),
      }),
  };
}
