import { auth } from "./cs/auth";
import { common } from "./cs/common";
import { fields } from "./cs/fields";
import { leagues } from "./cs/leagues";
import { players } from "./cs/players";
import { publicView } from "./cs/publicView";
import { results } from "./cs/results";
import { shell } from "./cs/shell";
import { standings } from "./cs/standings";
import { tournaments } from "./cs/tournaments";
import type { Messages } from "./en";

export const cs: Messages = {
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
