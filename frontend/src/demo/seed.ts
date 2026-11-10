// The demo's data: one league with 16 players and its current season, two
// finished tournaments with results, and a DYP tournament running its round
// robin tonight (PRD §5.1). The same seed gives the same data every time.
import type {
  EntryRead,
  GameRead,
  LeagueRead,
  LeagueSettings,
  MatchRead,
  Me,
  PhaseRead,
  Player,
  RoundRead,
  SeasonRead,
  TournamentRead,
} from "./contract";
import {
  createRng,
  drawDypPairs,
  fillFields,
  knockoutFirstRound,
  randomGame,
  roundRobinRounds,
  roundRobinStandings,
  waitingMatches,
} from "./engine";
import { DEFAULT_PLACEMENT_POINTS } from "./rules";

/** Ids in UUIDv7 form; fixed, so links into the demo stay valid. */
export function demoId(n: number): string {
  return `019a0000-0000-7000-8000-${n.toString(16).padStart(12, "0")}`;
}

export const DEMO_USER_ID = demoId(1);
export const DEMO_LEAGUE_ID = demoId(2);
export const DEMO_SEASON_ID = demoId(3);
export const DEMO_SHARE_TOKEN = "demo-share-token-k3vQ9xLr2TbW8sNe";
export const DEMO_EMAIL = "organizer@demo.tourneyhub.test";

export interface StoredLeague {
  league: LeagueRead;
  owner_id: string;
  settings: Omit<LeagueSettings, "name" | "placement_points">;
}
export interface StoredPlayer extends Player {
  league_id: string;
}
export interface StoredSeason extends SeasonRead {
  league_id: string;
}
export interface StoredTournament extends Omit<
  TournamentRead,
  "waiting" | "places"
> {
  league_id: string;
}

export interface DemoState {
  me: Me;
  leagues: StoredLeague[];
  players: StoredPlayer[];
  seasons: StoredSeason[];
  tournaments: StoredTournament[];
}

const PLAYER_NAMES = [
  "Anna Nováková",
  "Petr Svoboda",
  "Jana Dvořáková",
  "Tomáš Černý",
  "Eva Procházková",
  "Lukáš Kučera",
  "Kateřina Veselá",
  "Jakub Horák",
  "Lucie Němcová",
  "Ondřej Marek",
  "Tereza Pokorná",
  "Martin Král",
  "Barbora Růžičková",
  "David Beneš",
  "Veronika Fialová",
  "Filip Šimek",
];

function isoDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function at(date: string, time: string): string {
  return `${date}T${time}:00Z`;
}

/** Builds a tournament's rows; ids come from one counter per tournament. */
class TournamentBuilder {
  private next: number;
  readonly tournament: StoredTournament;

  constructor(
    base: number,
    summary: Pick<StoredTournament, "name" | "date" | "type" | "state">,
  ) {
    this.next = base;
    this.tournament = {
      id: demoId(base),
      league_id: DEMO_LEAGUE_ID,
      season_id: DEMO_SEASON_ID,
      goals_per_game: 10,
      phases: [],
      entries: [],
      rounds: [],
      fields: [],
      ...summary,
    };
  }

  id(): string {
    this.next += 1;
    return demoId(this.next);
  }

  phase(fields: Omit<PhaseRead, "id" | "position">): PhaseRead {
    const phase: PhaseRead = {
      id: this.id(),
      position: this.tournament.phases.length + 1,
      ...fields,
    };
    this.tournament.phases.push(phase);
    return phase;
  }

  entry(playerIds: string[], seed: number): EntryRead {
    const entry: EntryRead = {
      id: this.id(),
      stage: "main",
      kind: playerIds.length === 1 ? "player" : "pair",
      seed,
      player_ids: playerIds,
      is_disabled: false,
      is_top_player: false,
    };
    this.tournament.entries.push(entry);
    return entry;
  }

  round(
    phase: PhaseRead,
    pairs: [EntryRead, EntryRead][],
    sittingOut: EntryRead[] = [],
  ): RoundRead {
    const round: RoundRead = {
      id: this.id(),
      phase_id: phase.id,
      round_no:
        this.tournament.rounds.filter((r) => r.phase_id === phase.id).length +
        1,
      matches: [],
      sitting_out: sittingOut.map((entry) => entry.id),
    };
    round.matches = pairs.map(([a, b], index) => ({
      id: this.id(),
      round_id: round.id,
      position: index + 1,
      kind: "standard",
      sides: [
        { entry_id: a.id, player_ids: a.player_ids, is_bye: false },
        { entry_id: b.id, player_ids: b.player_ids, is_bye: false },
      ],
      outcome: null,
      is_walkover: false,
      games: [],
      result_entered_at: null,
    }));
    this.tournament.rounds.push(round);
    return round;
  }

  fields(count: number): void {
    for (let number = 1; number <= count; number++) {
      this.tournament.fields.push({ id: this.id(), number, match_id: null });
    }
  }
}

/** The value, which the seed's own construction guarantees. */
function required<T>(value: T | undefined): T {
  if (value === undefined) {
    throw new Error("The demo seed is inconsistent");
  }
  return value;
}

function play(
  match: MatchRead,
  rng: () => number,
  goalsPerGame: number,
  gamesToWin: number,
  enteredAt: string,
): void {
  const games: GameRead[] = [];
  const wins = { side_1: 0, side_2: 0 };
  while (wins.side_1 < gamesToWin && wins.side_2 < gamesToWin) {
    const game = randomGame(rng, goalsPerGame);
    if (game.winner !== "draw") {
      wins[game.winner] += 1;
    }
    games.push({ game_no: games.length + 1, ...game });
  }
  match.games = games;
  match.outcome = wins.side_1 > wins.side_2 ? "side_1" : "side_2";
  match.result_entered_at = enteredAt;
}

const ROUND_ROBIN: Omit<PhaseRead, "id" | "position"> = {
  kind: "group",
  format: "round_robin",
  round_robin_legs: 1,
  sit_out_points: 0,
  tiebreakers: null,
  qualifiers: null,
  third_place_match: null,
  monster_knockout_mode: null,
  match_format: "bo1",
  final_match_format: null,
};

function octoberSingles(
  players: StoredPlayer[],
  rng: () => number,
): StoredTournament {
  const date = "2026-10-15";
  const t = new TournamentBuilder(1000, {
    name: "October Singles",
    date,
    type: "singles",
    state: "finished",
  });
  const group = t.phase(ROUND_ROBIN);
  const entries = players
    .slice(0, 6)
    .map((player, i) => t.entry([player.id], i + 1));
  for (const pairing of roundRobinRounds(entries)) {
    const round = t.round(group, pairing.matches, pairing.sittingOut);
    for (const match of round.matches) {
      play(match, rng, t.tournament.goals_per_game, 1, at(date, "19:30"));
    }
  }
  t.fields(1);
  return t.tournament;
}

function autumnOpenDyp(
  players: StoredPlayer[],
  rng: () => number,
): StoredTournament {
  const date = "2026-10-29";
  const t = new TournamentBuilder(2000, {
    name: "Autumn Open DYP",
    date,
    type: "dyp",
    state: "finished",
  });
  const group = t.phase(ROUND_ROBIN);
  const knockout = t.phase({
    ...ROUND_ROBIN,
    kind: "knockout",
    format: "single_elimination",
    round_robin_legs: null,
    sit_out_points: null,
    qualifiers: 4,
    third_place_match: false,
    final_match_format: "bo3",
  });
  const { pairs } = drawDypPairs(
    players.slice(4, 12).map((player) => player.id),
    rng,
  );
  const entries = pairs.map((pair, i) => t.entry(pair, i + 1));
  for (const pairing of roundRobinRounds(entries)) {
    const round = t.round(group, pairing.matches, pairing.sittingOut);
    for (const match of round.matches) {
      play(match, rng, t.tournament.goals_per_game, 1, at(date, "19:45"));
    }
  }
  const order = roundRobinStandings(
    entries.map((entry) => entry.id),
    t.tournament.rounds,
    0,
  ).map((row) => required(entries.find((entry) => entry.id === row.entry_id)));
  const semifinals = t.round(knockout, knockoutFirstRound(order.slice(0, 4)));
  for (const match of semifinals.matches) {
    play(match, rng, t.tournament.goals_per_game, 1, at(date, "21:00"));
  }
  const [first, second] = semifinals.matches.map((match) =>
    required(
      entries.find(
        (entry) =>
          entry.id === match.sides[match.outcome === "side_2" ? 1 : 0].entry_id,
      ),
    ),
  );
  const final = t.round(knockout, [[required(first), required(second)]]);
  for (const match of final.matches) {
    play(match, rng, t.tournament.goals_per_game, 2, at(date, "21:30"));
  }
  t.fields(2);
  return t.tournament;
}

function thursdayDyp(
  players: StoredPlayer[],
  rng: () => number,
  date: string,
): StoredTournament {
  const t = new TournamentBuilder(3000, {
    name: "Thursday DYP",
    date,
    type: "dyp",
    state: "in_progress",
  });
  const group = t.phase(ROUND_ROBIN);
  const { pairs } = drawDypPairs(
    players.slice(0, 12).map((player) => player.id),
    rng,
  );
  const entries = pairs.map((pair, i) => t.entry(pair, i + 1));
  const rounds = roundRobinRounds(entries).map((pairing) =>
    t.round(group, pairing.matches, pairing.sittingOut),
  );
  // Rounds 1 and 2 are played, and the first match of round 3.
  const played = [
    ...(rounds[0]?.matches ?? []),
    ...(rounds[1]?.matches ?? []),
    ...(rounds[2]?.matches.slice(0, 1) ?? []),
  ];
  for (const match of played) {
    play(match, rng, t.tournament.goals_per_game, 1, at(date, "19:15"));
  }
  t.fields(2);
  const matchesById = new Map(
    t.tournament.rounds
      .flatMap((round) => round.matches)
      .map((match) => [match.id, match]),
  );
  t.tournament.fields = fillFields(
    t.tournament.fields,
    waitingMatches(t.tournament.rounds, t.tournament.fields),
    matchesById,
  );
  return t.tournament;
}

/** A fresh copy of the demo data; `today` dates the running tournament. */
export function createSeed(today: Date = new Date()): DemoState {
  const rng = createRng(20261110);
  const players: StoredPlayer[] = PLAYER_NAMES.map((name, i) => ({
    id: demoId(100 + i),
    league_id: DEMO_LEAGUE_ID,
    name,
    removed_at: null,
  }));
  const tournaments = [
    octoberSingles(players, rng),
    autumnOpenDyp(players, rng),
    thursdayDyp(players, rng, isoDate(today)),
  ];
  return {
    me: {
      id: DEMO_USER_ID,
      email: DEMO_EMAIL,
      display_name: "Alex Organizer",
      language: "en",
      is_admin: false,
    },
    leagues: [
      {
        league: {
          id: DEMO_LEAGUE_ID,
          name: "Thursday Foosball",
          created_at: "2026-09-01T18:00:00Z",
          updated_at: null,
        },
        owner_id: DEMO_USER_ID,
        settings: {
          draws_allowed: false,
          default_field_count: 2,
          default_match_format: "bo1",
          default_goals_per_game: 10,
          share_token: DEMO_SHARE_TOKEN,
        },
      },
    ],
    players,
    seasons: [
      {
        id: DEMO_SEASON_ID,
        league_id: DEMO_LEAGUE_ID,
        number: 1,
        name: null,
        state: "active",
        placement_points: [...DEFAULT_PLACEMENT_POINTS],
        started_at: "2026-09-01T18:00:00Z",
        closed_at: null,
      },
    ],
    tournaments,
  };
}
