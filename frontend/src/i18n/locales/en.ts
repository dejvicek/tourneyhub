// The English texts are the reference: every other language has the same
// keys. Each area keeps its texts in its own module under en/ and cs/, so
// that screens built in parallel do not edit the same file; they merge here
// into the one namespace.
import { auth } from "./en/auth";
import { common } from "./en/common";
import { fields } from "./en/fields";
import { leagues } from "./en/leagues";
import { players } from "./en/players";
import { publicView } from "./en/publicView";
import { results } from "./en/results";
import { roundRobin } from "./en/roundRobin";
import { shell } from "./en/shell";
import { standings } from "./en/standings";
import { tournaments } from "./en/tournaments";

export const en = {
  ...common,
  shell,
  auth,
  leagues,
  players,
  standings,
  tournaments,
  fields,
  results,
  publicView,
  // play
  roundRobin,
};

export type Messages = typeof en;

/** The base of an English plural key: "players" for "players_one" or "players_other". */
type PluralBase<K> = K extends `${infer Base}_one`
  ? Base
  : K extends `${infer Base}_other`
    ? Base
    : never;

/**
 * The Czech texts for the English reference `T`: the same keys, plus
 * `_few` (2–4) and `_many` (decimals) for each key that English has as
 * `_one` or `_other`, which Czech plurals need (docs/frontend-style.md §7).
 */
export type CsMessages<T = Messages> = T extends string
  ? string
  : { [K in keyof T]: CsMessages<T[K]> } & {
      [K in PluralBase<keyof T> as `${K}_few` | `${K}_many`]?: string;
    };
