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
};

export type Messages = typeof en;
