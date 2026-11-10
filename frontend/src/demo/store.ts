// The demo's in-memory store. It lives as long as the page: a reload starts
// again from the seed. Handlers read and change it through the functions
// here, which also compute what the backend computes on read (ADR-009).
import type {
  LeagueRead,
  PlaceRow,
  PublicLeague,
  SeasonStandingRow,
  TournamentRead,
  TournamentStandingRow,
  TournamentSummary,
} from "./contract";
import {
  placesAfterFourKnockout,
  roundRobinStandings,
  seasonStandings,
  waitingMatches,
  withPoints,
} from "./engine";
import { placesOf, syncBracket } from "./finalsEngine";
import { rules } from "./rules";
import {
  createSeed,
  type DemoState,
  type StoredLeague,
  type StoredSeason,
  type StoredTournament,
} from "./seed";
import { createOutsideState, type OutsideState } from "./seedOutside";

let state: DemoState = createSeed();

/** A stored row as the API returns it, without the league it belongs to. */
export function withoutLeague<T extends { league_id: string }>(
  row: T,
): Omit<T, "league_id"> {
  const copy: Partial<T> = { ...row };
  delete copy.league_id;
  // Only league_id was removed, and it was present.
  return copy as Omit<T, "league_id">;
}

/** The current data, for handlers to read and change. */
export function db(): DemoState {
  return state;
}

/** Back to the seed; tests call it after each test. */
export function resetDemoStore(): void {
  state = createSeed();
}

export function findLeague(leagueId: string): StoredLeague | undefined {
  return state.leagues.find((row) => row.id === leagueId);
}

export function activeSeason(leagueId: string): StoredSeason | undefined {
  return state.seasons.find(
    (season) => season.league_id === leagueId && season.state === "active",
  );
}

export function findTournament(
  leagueId: string,
  tournamentId: string,
): StoredTournament | undefined {
  return state.tournaments.find(
    (t) => t.id === tournamentId && t.league_id === leagueId,
  );
}

/** The seasons of a league, oldest first, as the API returns them. */
export function seasonsOf(leagueId: string): StoredSeason[] {
  return state.seasons
    .filter((season) => season.league_id === leagueId)
    .toSorted((a, b) => a.number - b.number);
}

/** A league as GET /api/v1/leagues/{league_id} returns it (LeagueRead). */
export function leagueRead(row: StoredLeague): LeagueRead {
  const league: Partial<StoredLeague> = { ...row };
  delete league.owner_id;
  return {
    // Only owner_id was removed, and it was present.
    ...(league as Omit<StoredLeague, "owner_id">),
    seasons: seasonsOf(row.id).map(withoutLeague),
  };
}

/** The phase being played and whether its matches drawn so far are played. */
function currentPhase(
  t: StoredTournament,
): Pick<TournamentSummary, "current_phase_id" | "current_phase_done"> {
  const current = t.phases
    .toSorted((a, b) => b.position - a.position)
    .find((phase) => t.rounds.some((round) => round.phase_id === phase.id));
  if (!current) {
    return { current_phase_id: null, current_phase_done: false };
  }
  return {
    current_phase_id: current.id,
    current_phase_done: t.rounds
      .filter((round) => round.phase_id === current.id)
      .every((round) => round.matches.every((m) => m.outcome !== null)),
  };
}

export function tournamentSummary(t: StoredTournament): TournamentSummary {
  syncBracket(t); // finals: the last knockout result finishes the tournament (FR-037)
  return {
    id: t.id,
    season_id: t.season_id,
    name: t.name,
    date: t.date,
    type: t.type,
    state: t.state,
    phases: t.phases.map(({ id, position, kind, format }) => ({
      id,
      position,
      kind,
      format,
    })),
    ...currentPhase(t),
  };
}

/** demo only, the engine decides: the group-phase standings. */
export function tournamentStandings(
  t: StoredTournament,
): TournamentStandingRow[] {
  const group = t.phases.find((phase) => phase.kind === "group");
  if (!group) {
    return [];
  }
  const sitOutPoints =
    group.sit_out_points === 1 ? rules.sitOutPointsWhenOn : 0;
  return roundRobinStandings(
    t.entries.filter((entry) => entry.stage === "main").map((e) => e.id),
    t.rounds.filter((round) => round.phase_id === group.id),
    sitOutPoints,
  );
}

function places(t: StoredTournament): PlaceRow[] | null {
  if (t.state !== "finished") {
    return null;
  }
  const table =
    state.seasons.find((season) => season.id === t.season_id)
      ?.placement_points ?? [];
  // finals: knockouts of any size, Swiss and Monster DYP (finalsEngine.ts)
  const detailed = placesOf(t, table);
  if (detailed) {
    return detailed.rows;
  }
  const groupOrder = tournamentStandings(t);
  const knockout = t.phases.find((phase) => phase.kind === "knockout");
  if (!knockout) {
    return withPoints(
      groupOrder.map(({ place, entry_id }) => ({ place, entry_id })),
      table,
    );
  }
  const [semifinals, final] = t.rounds.filter(
    (round) => round.phase_id === knockout.id,
  );
  const finalMatch = final?.matches[0];
  if (!semifinals || !finalMatch) {
    return null;
  }
  return withPoints(
    placesAfterFourKnockout(
      semifinals.matches,
      finalMatch,
      groupOrder.map((row) => row.entry_id),
    ),
    table,
  );
}

export function tournamentRead(t: StoredTournament): TournamentRead {
  syncBracket(t); // finals: the winners move on, the tournament finishes (FR-037)
  return {
    ...withoutLeague(t),
    ...currentPhase(t),
    waiting: waitingMatches(t.rounds, t.fields).map((match) => match.id),
    places: places(t),
  };
}

export function seasonStandingsOf(seasonId: string): SeasonStandingRow[] {
  return seasonStandings(
    state.tournaments
      .filter((t) => t.season_id === seasonId && t.state === "finished")
      .map((t) => ({
        places: places(t) ?? [],
        members: new Map(t.entries.map((e) => [e.id, e.player_ids])),
      })),
  );
}

export function publicLeague(shareToken: string): PublicLeague | undefined {
  const row = state.leagues.find((league) => league.share_token === shareToken);
  if (!row) {
    return undefined;
  }
  const leagueId = row.id;
  const season = activeSeason(leagueId);
  return {
    name: row.name,
    seasons: state.seasons
      .filter((s) => s.league_id === leagueId)
      .map(withoutLeague),
    players: state.players
      .filter((player) => player.league_id === leagueId)
      .map(withoutLeague),
    // FR-070: tournaments in setup are visible only to the organizer.
    tournaments: state.tournaments
      .filter((t) => t.season_id === season?.id && t.state !== "setup")
      .map(tournamentSummary),
    standings: season ? seasonStandingsOf(season.id) : [],
  };
}

// ---------------------------------------------------------------- outside (auth)
// Accounts and sessions are no rows of DemoState; they live next to it and
// start again with it: a new DemoState after resetDemoStore() gets a fresh
// OutsideState.

const outsideByState = new WeakMap<DemoState, OutsideState>();

export function outsideDb(): OutsideState {
  let outside = outsideByState.get(state);
  if (outside === undefined) {
    outside = createOutsideState(state.me);
    outsideByState.set(state, outside);
  }
  return outside;
}
