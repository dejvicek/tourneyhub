import { auth } from "./cs/auth";
import { common } from "./cs/common";
import { fields } from "./cs/fields";
import { finals } from "./cs/finals";
import { leagues } from "./cs/leagues";
import { players } from "./cs/players";
import { publicView } from "./cs/publicView";
import { results } from "./cs/results";
import { roundRobin } from "./cs/roundRobin";
import { shell } from "./cs/shell";
import { standings } from "./cs/standings";
import { tournaments } from "./cs/tournaments";
import type { CsMessages } from "./en";

export const cs: CsMessages = {
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
  finals,
};
