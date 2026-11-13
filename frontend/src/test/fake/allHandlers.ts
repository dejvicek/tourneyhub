// Every handler of the demo's fake API, one module per area (src/demo/README.md).
import { adminHandlers } from "./handlers/admin";
import { authHandlers } from "./handlers/auth";
import { fieldHandlers } from "./handlers/fields";
import { finalsHandlers } from "./handlers/finals";
import { leagueHandlers } from "./handlers/leagues";
import { playHandlers } from "./handlers/play";
import { playerHandlers } from "./handlers/players";
import { publicHandlers } from "./handlers/public";
import { resultHandlers } from "./handlers/results";
import { standingsHandlers } from "./handlers/standings";
import { tournamentHandlers } from "./handlers/tournaments";

export const fakeHandlers = [
  ...authHandlers,
  ...adminHandlers,
  ...leagueHandlers,
  ...playerHandlers,
  ...standingsHandlers,
  ...tournamentHandlers,
  ...fieldHandlers,
  ...resultHandlers,
  ...publicHandlers,
  // play
  ...playHandlers,
  // finals
  ...finalsHandlers,
];
