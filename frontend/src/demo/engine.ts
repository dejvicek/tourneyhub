// demo only, the engine decides
//
// Simple stand-ins for the tournament engine (backend tourneyhub.engine,
// ADR-009), so that the fake API returns schedules, draws, standings and
// places that look plausible. They follow PRD.md loosely and src/demo/rules.ts
// for the rules still open; none of this is the real behaviour.
import type {
  FieldRead,
  MatchFormat,
  MatchRead,
  Outcome,
  PlaceRow,
  RoundRead,
  SeasonStandingRow,
  TournamentStandingRow,
} from "./contract";
import { MATCH_POINTS, type RoundRobinOrder, rules } from "./rules";

/** A seeded pseudo-random generator (mulberry32), so every seed is the same. */
export function createRng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffled<T>(items: readonly T[], rng: () => number): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [result[i], result[j]] = [result[j] as T, result[i] as T];
  }
  return result;
}

export interface Pairing<T> {
  matches: [T, T][];
  sittingOut: T[];
}

/** demo only, the engine decides: round-robin rounds by the circle method (BR-050, BR-051). */
export function roundRobinRounds<T>(
  entries: readonly T[],
  order: RoundRobinOrder = rules.roundRobinOrder,
): Pairing<T>[] {
  const slots: (T | null)[] = [...entries];
  if (slots.length % 2 === 1) {
    slots.push(null);
  }
  const rounds: Pairing<T>[] = [];
  const [fixed, ...rest] = slots;
  for (let round = 0; round < slots.length - 1; round++) {
    const rotated = [
      ...rest.slice(rest.length - round),
      ...rest.slice(0, rest.length - round),
    ];
    const line = [fixed ?? null, ...rotated];
    const pairing: Pairing<T> = { matches: [], sittingOut: [] };
    for (let i = 0; i < line.length / 2; i++) {
      const a = line[i] ?? null;
      const b = line[line.length - 1 - i] ?? null;
      if (a !== null && b !== null) {
        pairing.matches.push([a, b]);
      } else if (a !== null || b !== null) {
        pairing.sittingOut.push((a ?? b) as T);
      }
    }
    rounds.push(pairing);
  }
  switch (order) {
    case "circle":
      return rounds;
    case "top_seeds_last":
      return rounds.reverse();
  }
}

/**
 * demo only, the engine decides: a DYP draw (BR-031–BR-033). The ranked
 * players split into a top and a bottom half; with an odd number the lot
 * leaves one out first.
 */
export function drawDypPairs<T>(
  ranked: readonly T[],
  rng: () => number,
): { pairs: [T, T][]; leftOut: T | null } {
  let players = [...ranked];
  let leftOut: T | null = null;
  if (players.length % 2 === 1) {
    const index = Math.floor(rng() * players.length);
    leftOut = players[index] ?? null;
    players = players.filter((_, i) => i !== index);
  }
  const half = players.length / 2;
  const top = players.slice(0, half);
  const bottom = shuffled(players.slice(half), rng);
  return {
    pairs: top.map((player, i) => [player, bottom[i] as T]),
    leftOut,
  };
}

/** demo only, the engine decides: round 1 of a bracket, 1 v N, 2 v N-1 … (seeds in order). */
export function knockoutFirstRound<T>(seeds: readonly T[]): [T, T][] {
  const matches: [T, T][] = [];
  for (let i = 0; i < seeds.length / 2; i++) {
    matches.push([seeds[i] as T, seeds[seeds.length - 1 - i] as T]);
  }
  return matches;
}

/** demo only: a plausible game, the winner reaching the goals per game. */
export function randomGame(
  rng: () => number,
  goalsPerGame: number,
): { winner: Outcome; score_1: number; score_2: number } {
  const loserGoals = Math.floor(rng() * goalsPerGame);
  return rng() < 0.5
    ? { winner: "side_1", score_1: goalsPerGame, score_2: loserGoals }
    : { winner: "side_2", score_1: loserGoals, score_2: goalsPerGame };
}

function scoreDifference(match: MatchRead, side: 0 | 1): number {
  let difference = 0;
  for (const game of match.games) {
    if (game.score_1 !== null && game.score_2 !== null) {
      difference +=
        side === 0 ? game.score_1 - game.score_2 : game.score_2 - game.score_1;
    }
  }
  return difference;
}

/** BR-101: the games a walkover counts for its winner, those needed to win. */
const WALKOVER_GAMES: Record<MatchFormat, number> = {
  bo1: 1,
  bo2: 2,
  bo3: 2,
  bo5: 3,
};

/** demo only, the engine decides: games won minus lost by one side (BR-101). */
export function gameDifference(
  match: MatchRead,
  side: 0 | 1,
  matchFormat: MatchFormat,
): number {
  const mine: Outcome = side === 0 ? "side_1" : "side_2";
  if (match.is_walkover) {
    const games = WALKOVER_GAMES[matchFormat];
    return match.outcome === mine ? games : -games;
  }
  let difference = 0;
  for (const game of match.games) {
    if (game.winner !== "draw") {
      difference += game.winner === mine ? 1 : -1;
    }
  }
  return difference;
}

/**
 * demo only, the engine decides: round-robin standings (BR-070, BR-101), with
 * the tie-breakers of rules.roundRobinTiebreakers. A sit-out is counted but
 * earns no points here: only Swiss and Monster DYP score it (BR-071).
 */
export function roundRobinStandings(
  entryIds: readonly string[],
  rounds: readonly RoundRead[],
  matchFormat: MatchFormat = "bo1",
): TournamentStandingRow[] {
  const rows = new Map<string, Omit<TournamentStandingRow, "place">>(
    entryIds.map((entry_id) => [
      entry_id,
      {
        entry_id,
        played: 0,
        won: 0,
        drawn: 0,
        lost: 0,
        sat_out: 0,
        points: 0,
        game_difference: 0,
        score_difference: 0,
        bh1: null,
        bh2: null,
      },
    ]),
  );
  const played: MatchRead[] = [];
  for (const round of rounds) {
    // A sit-out counts once its round is played, as in the backend (P8).
    const over = round.matches.every((match) => match.outcome !== null);
    for (const entryId of over ? round.sitting_out : []) {
      const row = rows.get(entryId);
      if (row) {
        row.sat_out += 1;
      }
    }
    for (const match of round.matches) {
      if (match.outcome === null) {
        continue;
      }
      played.push(match);
      match.sides.forEach((side, index) => {
        const row =
          side.entry_id === null ? undefined : rows.get(side.entry_id);
        if (!row) {
          return;
        }
        const mine: Outcome = index === 0 ? "side_1" : "side_2";
        row.played += 1;
        row.game_difference += gameDifference(
          match,
          index === 0 ? 0 : 1,
          matchFormat,
        );
        row.score_difference += scoreDifference(match, index === 0 ? 0 : 1);
        if (match.outcome === "draw") {
          row.drawn += 1;
          row.points += MATCH_POINTS.draw;
        } else if (match.outcome === mine) {
          row.won += 1;
          row.points += MATCH_POINTS.win;
        } else {
          row.lost += 1;
          row.points += MATCH_POINTS.loss;
        }
      });
    }
  }

  const headToHead = (a: string, b: string): number => {
    let points = 0;
    for (const match of played) {
      const ids = match.sides.map((side) => side.entry_id);
      if (ids.includes(a) && ids.includes(b)) {
        const aSide: Outcome = ids[0] === a ? "side_1" : "side_2";
        points +=
          match.outcome === aSide ? 1 : match.outcome === "draw" ? 0 : -1;
      }
    }
    return points;
  };

  const sorted = [...rows.values()].sort((a, b) => b.points - a.points);
  const compare = (
    a: Omit<TournamentStandingRow, "place">,
    b: Omit<TournamentStandingRow, "place">,
    levelCount: number,
  ): number => {
    for (const tiebreaker of rules.roundRobinTiebreakers) {
      switch (tiebreaker) {
        case "head_to_head":
          if (levelCount === 2) {
            const result = headToHead(b.entry_id, a.entry_id);
            if (result !== 0) {
              return result;
            }
          }
          break;
        case "score_difference":
          if (a.score_difference !== b.score_difference) {
            return b.score_difference - a.score_difference;
          }
          break;
        case "game_difference":
          if (a.game_difference !== b.game_difference) {
            return b.game_difference - a.game_difference;
          }
          break;
      }
    }
    return 0;
  };
  const ordered: Omit<TournamentStandingRow, "place">[] = [];
  for (let i = 0; i < sorted.length;) {
    const level = sorted.filter((row) => row.points === sorted[i]?.points);
    ordered.push(...level.sort((a, b) => compare(a, b, level.length)));
    i += level.length;
  }
  const result: TournamentStandingRow[] = [];
  ordered.forEach((row, index) => {
    const previous = result[index - 1];
    const prevRow = ordered[index - 1];
    const shared =
      previous !== undefined &&
      prevRow?.points === row.points &&
      compare(
        prevRow,
        row,
        ordered.filter((other) => other.points === row.points).length,
      ) === 0;
    result.push({ ...row, place: shared ? previous.place : index + 1 });
  });
  return result;
}

/** demo only, the engine decides: the points of a place shared by several entries (BR-110, BR-111). */
export function splitPlacementPoints(
  table: readonly number[],
  place: number,
  sharing: number,
): number {
  let total = 0;
  for (let p = place; p < place + sharing; p++) {
    total += table[p - 1] ?? 0;
  }
  return Math.floor(total / sharing);
}

/** demo only, the engine decides: placement points for every place (BR-110, BR-111). */
export function withPoints(
  places: readonly Omit<PlaceRow, "points_per_player">[],
  table: readonly number[],
): PlaceRow[] {
  return places.map((row) => ({
    ...row,
    points_per_player: splitPlacementPoints(
      table,
      row.place,
      places.filter((other) => other.place === row.place).length,
    ),
  }));
}

/**
 * demo only, the engine decides: places after a 4-entry knockout without a
 * third-place match (BR-102, BR-103): the semifinal losers share 3rd, the
 * others follow in their group-phase order.
 */
export function placesAfterFourKnockout(
  semifinals: readonly MatchRead[],
  final: MatchRead,
  groupOrder: readonly string[],
): Omit<PlaceRow, "points_per_player">[] {
  const winner = (match: MatchRead) =>
    match.outcome === "side_2"
      ? match.sides[1].entry_id
      : match.sides[0].entry_id;
  const loser = (match: MatchRead) =>
    match.outcome === "side_2"
      ? match.sides[0].entry_id
      : match.sides[1].entry_id;
  const top = [
    { place: 1, entry_id: winner(final) },
    { place: 2, entry_id: loser(final) },
    ...semifinals.map((match) => ({ place: 3, entry_id: loser(match) })),
  ].filter(
    (row): row is { place: number; entry_id: string } => row.entry_id !== null,
  );
  const knockoutIds = new Set(top.map((row) => row.entry_id));
  const rest = groupOrder
    .filter((id) => !knockoutIds.has(id))
    .map((entry_id, index) => ({ place: top.length + index + 1, entry_id }));
  return [...top, ...rest];
}

/** demo only, the engine decides: season standings from finished tournaments (FR-061, §7.14). */
export function seasonStandings(
  results: readonly {
    places: readonly PlaceRow[];
    members: ReadonlyMap<string, readonly string[]>;
  }[],
): SeasonStandingRow[] {
  const rows = new Map<string, Omit<SeasonStandingRow, "place">>();
  for (const { places, members } of results) {
    for (const row of places) {
      for (const player_id of members.get(row.entry_id) ?? []) {
        const current = rows.get(player_id) ?? {
          player_id,
          points: 0,
          tournaments_played: 0,
          tournament_wins: 0,
        };
        current.points += row.points_per_player;
        current.tournaments_played += 1;
        current.tournament_wins += row.place === 1 ? 1 : 0;
        rows.set(player_id, current);
      }
    }
  }
  const sorted = [...rows.values()].sort(
    (a, b) => b.points - a.points || b.tournament_wins - a.tournament_wins,
  );
  const result: SeasonStandingRow[] = [];
  sorted.forEach((row, index) => {
    const previous = result[index - 1];
    const shared =
      previous?.points === row.points &&
      previous.tournament_wins === row.tournament_wins;
    result.push({ ...row, place: shared ? previous.place : index + 1 });
  });
  return result;
}

/**
 * demo only, the engine decides: the matches waiting for a field, in
 * schedule order (FR-092, BR-130): no result, not on a field, both sides known.
 */
export function waitingMatches(
  rounds: readonly RoundRead[],
  fields: readonly FieldRead[],
): MatchRead[] {
  const onField = new Set(fields.map((field) => field.match_id));
  return rounds
    .flatMap((round) => round.matches)
    .filter(
      (match) =>
        match.outcome === null &&
        !onField.has(match.id) &&
        match.sides.every((side) => !side.is_bye && side.player_ids.length > 0),
    );
}

/**
 * demo only, the engine decides: each free field, lowest number first, takes
 * the first waiting match none of whose players is on another field (BR-130,
 * BR-131). Returns the new placements.
 */
export function fillFields(
  fields: readonly FieldRead[],
  waiting: readonly MatchRead[],
  matchesById: ReadonlyMap<string, MatchRead>,
): FieldRead[] {
  const result = fields.map((field) => ({ ...field }));
  const busy = new Set(
    result.flatMap((field) =>
      field.match_id === null
        ? []
        : (matchesById
            .get(field.match_id)
            ?.sides.flatMap((side) => side.player_ids) ?? []),
    ),
  );
  const queue = [...waiting];
  for (const field of [...result].sort((a, b) => a.number - b.number)) {
    if (field.match_id !== null) {
      continue;
    }
    const index = queue.findIndex((match) =>
      match.sides.every((side) =>
        side.player_ids.every((player) => !busy.has(player)),
      ),
    );
    const match = queue[index];
    if (match === undefined) {
      continue;
    }
    queue.splice(index, 1);
    field.match_id = match.id;
    for (const player of match.sides.flatMap((side) => side.player_ids)) {
      busy.add(player);
    }
  }
  return result;
}
