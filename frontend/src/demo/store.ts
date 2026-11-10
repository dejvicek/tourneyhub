// The demo's in-memory store. It lives as long as the page: a reload starts
// again from the seed. Handlers read and change it through the functions
// here, which also compute what the backend computes on read (ADR-009).
import type {
  LeagueSettings,
  LeagueSummary,
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
import { rules } from "./rules";
import {
  createSeed,
  type DemoState,
  type StoredLeague,
  type StoredSeason,
  type StoredTournament,
} from "./seed";

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
  return state.leagues.find((row) => row.league.id === leagueId);
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

export function leagueSettings(row: StoredLeague): LeagueSettings {
  return {
    ...row.settings,
    name: row.league.name,
    placement_points: activeSeason(row.league.id)?.placement_points ?? [],
  };
}

export function leagueSummary(row: StoredLeague): LeagueSummary | undefined {
  const season = activeSeason(row.league.id);
  if (!season) {
    return undefined;
  }
  return {
    id: row.league.id,
    name: row.league.name,
    active_season: withoutLeague(season),
    player_count: state.players.filter(
      (player) =>
        player.league_id === row.league.id && player.removed_at === null,
    ).length,
  };
}

export function tournamentSummary(t: StoredTournament): TournamentSummary {
  return {
    id: t.id,
    season_id: t.season_id,
    name: t.name,
    date: t.date,
    type: t.type,
    state: t.state,
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
  return {
    ...withoutLeague(t),
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
  const row = state.leagues.find(
    (league) => league.settings.share_token === shareToken,
  );
  if (!row) {
    return undefined;
  }
  const leagueId = row.league.id;
  const season = activeSeason(leagueId);
  return {
    name: row.league.name,
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
