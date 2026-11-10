import { generatePath } from "react-router";

import { usePlay } from "@/features/tournaments/play/usePlay";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

/** What the fields screens (6b–6d) share: the data and their links. */
export function useFieldsScreen() {
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const play = usePlay(leagueId, tournamentId);
  const params = { leagueId, tournamentId };
  return {
    ...play,
    leagueId,
    tournamentId,
    manageHref: generatePath(paths.editFields, params),
    resultHref: (matchId: string) =>
      generatePath(paths.fieldsResult, { ...params, matchId }),
    moveHref: (matchId: string) =>
      generatePath(paths.moveMatch, { ...params, matchId }),
  };
}
