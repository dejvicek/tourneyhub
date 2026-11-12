// The demo's in-memory store. It lives as long as the page: a reload starts
// again from the seed. Handlers read and change it through the functions
// here, which also compute what the backend computes on read (ADR-009).
import type { components } from "@/api/schema";

import type {
  LeagueRead,
  PlaceRow,
  PlacesRead,
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

/** How far a running tournament is (screen 1); null outside play. */
function progressOf(t: StoredTournament): TournamentSummary["progress"] {
  if (t.state !== "in_progress" || t.rounds.length === 0) {
    return null;
  }
  const matches = t.rounds.flatMap((round) => round.matches);
  const group = t.phases.find((phase) => phase.kind === "group");
  const knockout = t.phases.find((phase) => phase.kind === "knockout");
  const groupRounds = t.rounds.filter((round) => round.phase_id === group?.id);
  const current =
    groupRounds.find((round) =>
      round.matches.some((match) => match.outcome === null),
    ) ?? groupRounds.at(-1);
  return {
    round_no: current?.round_no ?? 1,
    round_count: groupRounds.length,
    matches_played: matches.filter((match) => match.outcome !== null).length,
    match_count: matches.length,
    in_knockout:
      knockout !== undefined &&
      t.rounds.some((round) => round.phase_id === knockout.id),
  };
}

export function tournamentSummary(t: StoredTournament): TournamentSummary {
  syncBracket(t); // finals: the last knockout result finishes the tournament (FR-037)
  const winners = places(t)?.filter((row) => row.place === 1);
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
    player_count: t.entries
      .filter((entry) => entry.stage === "main")
      .reduce((sum, entry) => sum + entry.player_ids.length, 0),
    progress: progressOf(t),
    winner_player_ids:
      winners === undefined
        ? null
        : t.entries
            .filter((entry) => winners.some((row) => row.entry_id === entry.id))
            .flatMap((entry) => entry.player_ids),
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
  return roundRobinStandings(
    t.entries.filter((entry) => entry.stage === "main").map((e) => e.id),
    t.rounds.filter((round) => round.phase_id === group.id),
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

/** The places with the reason for each, for the organizer and the share link alike. */
export function placesRead(t: StoredTournament): PlacesRead {
  syncBracket(t);
  const table =
    state.seasons.find((season) => season.id === t.season_id)
      ?.placement_points ?? [];
  const detailed = placesOf(t, table);
  if (detailed) {
    return detailed;
  }
  // A plain round robin: the base engine's places.
  return {
    complete: t.state === "finished",
    rows: (places(t) ?? []).map((row) => ({
      ...row,
      reason: {
        kind: "group_place" as const,
        round: null,
        score: null,
        opponent_entry_id: null,
        group_place: row.place,
        group_format: "round_robin" as const,
      },
    })),
  };
}

/** The whole tournament as GET …/tournaments/{tournament_id} returns it. */
export function tournamentRead(t: StoredTournament): TournamentRead {
  syncBracket(t); // finals: the winners move on, the tournament finishes (FR-037)
  return {
    ...withoutLeague(t),
    ...currentPhase(t),
    waiting: waitingMatches(t.rounds, t.fields).map((match) => match.id),
  };
}

/** A finished tournament's places; none before it finishes. */
export function finalPlaces(t: StoredTournament): PlaceRow[] {
  return places(t) ?? [];
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

/** The league of a share token (FR-070), without anything only its organizer sees. */
export function sharedLeague(shareToken: string): StoredLeague | undefined {
  return state.leagues.find((league) => league.share_token === shareToken);
}

export function publicLeague(
  row: StoredLeague,
): components["schemas"]["PublicLeagueRead"] {
  return {
    name: row.name,
    seasons: seasonsOf(row.id).map(withoutLeague),
    players: state.players
      .filter((player) => player.league_id === row.id)
      .map(({ id, name }) => ({ id, name })),
  };
}

/** A season's tournaments for viewers: those in setup only the organizer sees. */
export function publicTournaments(seasonId: string): TournamentSummary[] {
  return state.tournaments
    .filter((t) => t.season_id === seasonId && t.state !== "setup")
    .toSorted((a, b) => Number(a.date < b.date) - Number(a.date > b.date))
    .map(tournamentSummary);
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
