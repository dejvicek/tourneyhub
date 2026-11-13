import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { finalsQueries } from "@/features/finals/api";

type EntryRead = components["schemas"]["EntryRead"];

/** "Anna Nováková" → "Anna N.", the form the design shows in tables and brackets. */
export function shortName(fullName: string): string {
  const [first = fullName, ...rest] = fullName.trim().split(/\s+/);
  const last = rest.at(-1);
  return last === undefined ? first : `${first} ${last.charAt(0)}.`;
}

/** Names of players and entries, from the league's player list, removed players too. */
export function useRoster(
  leagueId: string,
  entries: readonly EntryRead[] | undefined,
) {
  const { t } = useTranslation();
  const players = useQuery(finalsQueries.namedPlayers(leagueId));
  const names = new Map(
    (players.data ?? []).map((p) => [p.id, shortName(p.name)] as const),
  );
  const player = (playerId: string): string =>
    names.get(playerId) ?? t("finals.common.unknown");

  /** A pair as "A & B", a player as "A". */
  const playersNames = (playerIds: readonly string[]): string => {
    const [first, second] = playerIds;
    return first !== undefined && second !== undefined && playerIds.length === 2
      ? t("finals.common.names.pair", {
          first: player(first),
          second: player(second),
        })
      : playerIds.map(player).join(", ");
  };
  /** The two players of a Monster DYP team as "A / B". */
  const team = (playerIds: readonly string[]): string => {
    const [first, second] = playerIds;
    return first !== undefined && second !== undefined && playerIds.length === 2
      ? t("finals.common.names.team", {
          first: player(first),
          second: player(second),
        })
      : playerIds.map(player).join(", ");
  };
  const entry = (entryId: string | null): string => {
    const found = entries?.find((e) => e.id === entryId);
    return found === undefined
      ? t("finals.common.unknown")
      : playersNames(found.player_ids);
  };
  return {
    player,
    entry,
    team,
    ready: players.data !== undefined && entries !== undefined,
  };
}

/** A calendar date "2026-11-05" as a local Date, for i18next's datetime format. */
export function localDate(isoDate: string): Date {
  const [year = 1970, month = 1, day = 1] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}
