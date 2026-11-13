import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";

import {
  entryPlayers,
  firstName,
  type PlayModel,
  shortName,
  sideNames,
} from "./model";

type MatchSideRead = components["schemas"]["MatchSideRead"];

const NO_SIDE = { player_ids: [] };

/** How the play screens name pairs and players, in the UI language. */
export function useNames(model: PlayModel | undefined) {
  const { t, i18n } = useTranslation();
  const list = new Intl.ListFormat(i18n.resolvedLanguage, {
    style: "long",
    type: "conjunction",
  });

  /** "Anna N. & Petr S." */
  const short = (names: readonly string[]): string => {
    const [a, b] = names.map(shortName);
    return b === undefined ? (a ?? "") : t("roundRobin.names.pair", { a, b });
  };
  /** "Anna and Petr" for a sentence. */
  const first = (names: readonly string[]): string =>
    list.format(names.map(firstName));

  return {
    short,
    first,
    side: (side: Pick<MatchSideRead, "player_ids">) =>
      model ? short(sideNames(model, side)) : "",
    sideFirst: (side: Pick<MatchSideRead, "player_ids">) =>
      model ? first(sideNames(model, side)) : "",
    entry: (entryId: string) =>
      model ? short(entryPlayers(model, entryId)) : "",
    entryFirst: (entryId: string) =>
      model ? first(entryPlayers(model, entryId)) : "",
    /** "Anna N. & Petr S. v Jana D. & Tomáš Č." */
    match: (sides: readonly MatchSideRead[]) =>
      t("roundRobin.names.versus", {
        a: model ? short(sideNames(model, sides[0] ?? NO_SIDE)) : "",
        b: model ? short(sideNames(model, sides[1] ?? NO_SIDE)) : "",
      }),
  };
}
