// demo only, the engine decides
//
// Stand-ins for the engine of the finals screens (backend tourneyhub.engine,
// ADR-009): knockout brackets with byes, tournament places, Swiss and Monster
// DYP standings with BH1 and BH2, naive pairing of the next round, and the
// knockout formed after Monster DYP rounds. Minimal and deterministic; the
// open rules of issue #24 are read from rules.ts.
import type {
  BracketMatch,
  BracketRead,
  BracketRound,
  BracketRoundName,
  EntryRead,
  KnockoutMatchState,
  KnockoutPreview,
  MatchFormat,
  MatchRead,
  MatchSideRead,
  Outcome,
  ParticipantRead,
  PhaseRead,
  PlaceDetail,
  PlaceReason,
  PlacesRead,
  RankingRead,
  RoundRead,
  SwissRankingRow,
} from "./contract";
import { createRng, roundRobinStandings, withPoints } from "./engine";
import {
  MATCH_POINTS,
  type MonsterKnockoutMode,
  rules,
  type SwissTiebreaker,
} from "./rules";
import type { StoredTournament } from "./seed";

type Ids = () => string;

/** The value, which the caller's own checks guarantee. */
export function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) {
    throw new Error("The demo engine is inconsistent");
  }
  return value;
}

// ---------------------------------------------------------------- notes

/** What the data model keeps per entry that the contract's EntryRead has no field for. */
export interface EntryNote {
  joined_round: number | null;
  disabled_since_round: number | null;
}

// A WeakMap keeps the notes with the tournament object: a reset of the store
// builds new objects and so drops them.
const notes = new WeakMap<StoredTournament, Map<string, EntryNote>>();

export function noteOf(t: StoredTournament, entryId: string): EntryNote {
  return (
    notes.get(t)?.get(entryId) ?? {
      joined_round: null,
      disabled_since_round: null,
    }
  );
}

export function setNote(
  t: StoredTournament,
  entryId: string,
  patch: Partial<EntryNote>,
): void {
  const byEntry = notes.get(t) ?? new Map<string, EntryNote>();
  byEntry.set(entryId, { ...noteOf(t, entryId), ...patch });
  notes.set(t, byEntry);
}

// ---------------------------------------------------------------- helpers

function shuffled<T>(items: readonly T[], rng: () => number): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [result[i], result[j]] = [result[j] as T, result[i] as T];
  }
  return result;
}

export function groupPhase(t: StoredTournament): PhaseRead | undefined {
  return t.phases.find((phase) => phase.kind === "group");
}

export function knockoutPhase(t: StoredTournament): PhaseRead | undefined {
  return t.phases.find((phase) => phase.kind === "knockout");
}

export function roundsOf(t: StoredTournament, phase: PhaseRead): RoundRead[] {
  return t.rounds
    .filter((round) => round.phase_id === phase.id)
    .sort((a, b) => a.round_no - b.round_no);
}

/** BR-068: log2 of the entries, rounded up (Monster DYP counts players). */
export function recommendedRounds(count: number): number {
  return Math.max(1, Math.ceil(Math.log2(Math.max(count, 1))));
}

/** The highest id number in use, so that new rows get fresh ones. */
export function highestIdNumber(
  tournaments: readonly StoredTournament[],
): number {
  let highest = 0;
  const see = (id: string) => {
    highest = Math.max(highest, Number.parseInt(id.slice(-12), 16));
  };
  for (const t of tournaments) {
    see(t.id);
    [...t.phases, ...t.entries, ...t.rounds, ...t.fields].forEach((row) => {
      see(row.id);
    });
    t.rounds
      .flatMap((round) => round.matches)
      .forEach((match) => {
        see(match.id);
      });
  }
  return highest;
}

// ---------------------------------------------------------------- bracket

/** BR-040: the smallest power of two that fits all entries. */
export function bracketSize(count: number): number {
  let size = 2;
  while (size < count) {
    size *= 2;
  }
  return size;
}

/** BR-042: the seeds in bracket order, so that 1 and 2 can meet only in the final. */
function seedSlots(size: number): number[] {
  let order = [1, 2];
  while (order.length < size) {
    const n = order.length * 2;
    order = order.flatMap((seed) => [seed, n + 1 - seed]);
  }
  return order;
}

const emptySide = (): MatchSideRead => ({
  entry_id: null,
  player_ids: [],
  is_bye: false,
});

function sideOfEntry(entry: EntryRead | null): MatchSideRead {
  return entry
    ? { entry_id: entry.id, player_ids: entry.player_ids, is_bye: false }
    : { entry_id: null, player_ids: [], is_bye: true };
}

/**
 * All rounds of a bracket for the entries in seed order (BR-040–BR-042): byes
 * go to the top seeds (BR-041); later rounds start empty and fill in as
 * results come (syncBracket). The third-place match sits in the final's round.
 */
export function drawKnockoutRounds(args: {
  ids: Ids;
  phaseId: string;
  seeded: readonly EntryRead[];
  thirdPlace: boolean;
}): RoundRead[] {
  const { ids, phaseId, seeded, thirdPlace } = args;
  const size = bracketSize(seeded.length);
  const slots = seedSlots(size);
  const roundCount = Math.log2(size);
  const rounds: RoundRead[] = [];
  for (let r = 1; r <= roundCount; r++) {
    const round: RoundRead = {
      id: ids(),
      phase_id: phaseId,
      round_no: r,
      matches: [],
      sitting_out: [],
    };
    const count = size / 2 ** r;
    for (let j = 0; j < count; j++) {
      const match: MatchRead = {
        id: ids(),
        round_id: round.id,
        position: j + 1,
        kind: "standard",
        sides: [emptySide(), emptySide()],
        outcome: null,
        is_walkover: false,
        games: [],
        result_entered_at: null,
      };
      if (r === 1) {
        const a = seeded[(slots[2 * j] ?? 0) - 1] ?? null;
        const b = seeded[(slots[2 * j + 1] ?? 0) - 1] ?? null;
        match.sides = [sideOfEntry(a), sideOfEntry(b)];
        if (a === null || b === null) {
          match.outcome = a === null ? "side_2" : "side_1";
        }
      }
      round.matches.push(match);
    }
    if (r === roundCount && thirdPlace) {
      round.matches.push({
        id: ids(),
        round_id: round.id,
        position: count + 1,
        kind: "third_place",
        sides: [emptySide(), emptySide()],
        outcome: null,
        is_walkover: false,
        games: [],
        result_entered_at: null,
      });
    }
    rounds.push(round);
  }
  return rounds;
}

function sideThat(
  match: MatchRead,
  which: "winner" | "loser",
): MatchSideRead | null {
  if (match.outcome === null || match.outcome === "draw") {
    return null;
  }
  const [one, two] = match.sides;
  const winning = match.outcome === "side_1" ? one : two;
  const side = which === "winner" ? winning : winning === one ? two : one;
  return side.is_bye || side.entry_id === null ? null : side;
}

function clearResult(match: MatchRead): void {
  match.outcome = null;
  match.is_walkover = false;
  match.games = [];
  match.result_entered_at = null;
}

/**
 * Puts the winners of finished matches into the sides of the matches they
 * feed (BR-094: changing a winner updates the sides of later matches), and
 * finishes the tournament once every knockout match has a result (FR-037) or
 * reopens it when one is cleared (BR-095).
 */
export function syncBracket(t: StoredTournament): void {
  const phase = knockoutPhase(t);
  if (!phase) {
    return;
  }
  const rounds = roundsOf(t, phase);
  rounds.forEach((round, index) => {
    const previous = rounds[index - 1];
    if (!previous) {
      return;
    }
    const standard = previous.matches.filter((m) => m.kind === "standard");
    round.matches.forEach((match, j) => {
      const take = match.kind === "third_place" ? "loser" : "winner";
      const feeders =
        match.kind === "third_place"
          ? [standard[0], standard[1]]
          : [standard[2 * j], standard[2 * j + 1]];
      feeders.forEach((feeder, k) => {
        const source = feeder ? sideThat(feeder, take) : null;
        const current = match.sides[k === 0 ? 0 : 1];
        if (current.entry_id !== (source?.entry_id ?? null)) {
          match.sides[k === 0 ? 0 : 1] = source
            ? { ...source, is_bye: false }
            : emptySide();
          clearResult(match);
        }
      });
    });
  });
  const played = rounds
    .flatMap((round) => round.matches)
    .filter((match) => !match.sides.some((side) => side.is_bye));
  const allDone = played.length > 0 && played.every((m) => m.outcome !== null);
  if (allDone && t.state === "in_progress") {
    t.state = "finished";
  } else if (!allDone && t.state === "finished") {
    t.state = "in_progress";
  }
}

function formatOf(
  phase: PhaseRead,
  match: MatchRead,
  isFinal: boolean,
): MatchFormat {
  return isFinal && match.kind === "standard"
    ? (phase.final_match_format ?? phase.match_format)
    : phase.match_format;
}

function scoreOf(
  match: MatchRead,
  format: MatchFormat,
): [number, number] | null {
  if (match.outcome === null || match.games.length === 0) {
    return null;
  }
  const first = match.games[0];
  const one = first?.score_1;
  const two = first?.score_2;
  if (format === "bo1" && typeof one === "number" && typeof two === "number") {
    return [one, two];
  }
  const tally: [number, number] = [0, 0];
  for (const game of match.games) {
    if (game.winner === "side_1") {
      tally[0] += 1;
    } else if (game.winner === "side_2") {
      tally[1] += 1;
    }
  }
  return tally;
}

function roundName(index: number, count: number): BracketRoundName {
  switch (count - 1 - index) {
    case 0:
      return "final";
    case 1:
      return "semifinal";
    case 2:
      return "quarterfinal";
    default:
      return "round_of_16";
  }
}

/**
 * BR-094: a knockout result is locked once a later match it feeds has one,
 * the next match for the winner and, for a semifinal, the third-place match
 * for the loser. That result has to be cleared first.
 */
export function knockoutLocked(t: StoredTournament, match: MatchRead): boolean {
  const phase = knockoutPhase(t);
  if (!phase || match.kind !== "standard") {
    return false;
  }
  const rounds = roundsOf(t, phase);
  const index = rounds.findIndex((round) =>
    round.matches.some((m) => m.id === match.id),
  );
  const next = rounds[index + 1];
  if (index < 0 || !next) {
    return false;
  }
  const fed = [
    next.matches.filter((m) => m.kind === "standard")[
      Math.floor((match.position - 1) / 2)
    ],
    ...next.matches.filter((m) => m.kind === "third_place"),
  ];
  return fed.some((m) => m !== undefined && m.outcome !== null);
}

/** The knockout as the bracket screen shows it; null without a knockout. */
export function bracketOf(t: StoredTournament): BracketRead | null {
  const phase = knockoutPhase(t);
  if (!phase) {
    return null;
  }
  const rounds = roundsOf(t, phase);
  const first = rounds[0];
  if (!first) {
    return null;
  }
  // The knockout's own seeds: where the first round put each entry (BR-042).
  const slots = seedSlots(first.matches.length * 2);
  const seedOf = new Map<string, number>();
  first.matches.forEach((match, j) => {
    match.sides.forEach((side, k) => {
      if (side.entry_id !== null) {
        seedOf.set(side.entry_id, slots[2 * j + k] ?? 0);
      }
    });
  });
  const fieldOf = new Map(
    t.fields.flatMap((field) =>
      field.match_id === null ? [] : [[field.match_id, field.number] as const],
    ),
  );
  const offset = t.rounds
    .filter((round) => round.phase_id !== phase.id)
    .reduce((sum, round) => sum + round.matches.length, 0);
  const numbers = new Map<string, number>();
  let next = offset;
  for (const match of rounds.flatMap((round) => round.matches)) {
    if (!match.sides.some((side) => side.is_bye)) {
      next += 1;
      numbers.set(match.id, next);
    }
  }
  const result: BracketRound[] = rounds.map((round, index) => ({
    round_no: round.round_no,
    name: roundName(index, rounds.length),
    matches: round.matches.map((match): BracketMatch => {
      const isFinal = index === rounds.length - 1;
      const known = match.sides.every((side) => side.entry_id !== null);
      const fieldNumber = fieldOf.get(match.id) ?? null;
      const state: KnockoutMatchState = match.sides.some((s) => s.is_bye)
        ? "bye"
        : match.outcome !== null
          ? "played"
          : !known
            ? "waiting"
            : fieldNumber !== null
              ? "on_field"
              : "ready";
      const nextRound = rounds[index + 1];
      const feeds =
        match.kind === "standard"
          ? nextRound?.matches.filter((m) => m.kind === "standard")[
              Math.floor((match.position - 1) / 2)
            ]
          : undefined;
      const format = formatOf(phase, match, isFinal);
      return {
        match_id: match.id,
        number: numbers.get(match.id) ?? null,
        round_no: round.round_no,
        position: match.position,
        kind: match.kind,
        state,
        sides: match.sides.map((side) => ({
          entry_id: side.entry_id,
          seed:
            side.entry_id === null ? null : (seedOf.get(side.entry_id) ?? null),
          is_bye: side.is_bye,
        })) as BracketMatch["sides"],
        outcome: match.outcome,
        is_walkover: match.is_walkover,
        score: scoreOf(match, format),
        match_format: format,
        field_number: fieldNumber,
        next_number: feeds ? (numbers.get(feeds.id) ?? null) : null,
        result_locked: knockoutLocked(t, match),
      };
    }),
  }));
  return {
    phase_id: phase.id,
    size: Math.max(first.matches.length * 2, 4),
    third_place_match: rounds.some((round) =>
      round.matches.some((match) => match.kind === "third_place"),
    ),
    has_group_phase: groupPhase(t) !== undefined,
    rounds: result,
  };
}

// ---------------------------------------------------------------- ranking

type Compared = Omit<SwissRankingRow, "place">;

/**
 * demo only: Swiss and Monster DYP standings (BR-070–BR-073). Entries are
 * players (Monster DYP, both of a team get the points) or pairs; a side's
 * members are found by their players.
 */
export function rankingOf(t: StoredTournament): RankingRead {
  const group = groupPhase(t);
  const mainEntries = t.entries.filter((entry) => entry.stage === "main");
  const tiebreakers = group?.tiebreakers ?? [...rules.swissTiebreakers];
  const entryOfPlayer = new Map(
    mainEntries.flatMap((entry) =>
      entry.player_ids.map((player) => [player, entry.id] as const),
    ),
  );
  const rows = new Map<string, Compared>(
    mainEntries.map((entry) => [
      entry.id,
      {
        entry_id: entry.id,
        played: 0,
        sat_out: 0,
        points: 0,
        bh1: 0,
        bh2: 0,
        score_difference: 0,
        is_disabled: entry.is_disabled,
      },
    ]),
  );
  // BR-071, BR-078: a Swiss or Monster DYP sit-out is worth the phase's points
  // for sitting out, which count as points in the standings. A round robin has
  // none (not even 0); this demo still gives it a value, which PR #65
  // (closes #59) removes. A missed round is no sit-out here and earns nothing (BR-064,
  // BR-067); only the sit-out order counts it (issue #60).
  const sitOutPoints = group?.sit_out_points ?? 0;
  const opponents = new Map<string, string[]>();
  const membersOf = (side: MatchSideRead): string[] => [
    ...new Set(
      side.player_ids.flatMap((player) => entryOfPlayer.get(player) ?? []),
    ),
  ];
  const rounds = group ? roundsOf(t, group) : [];
  for (const round of rounds) {
    for (const entryId of round.sitting_out) {
      const row = rows.get(entryId);
      if (row) {
        row.sat_out += 1;
        row.points += sitOutPoints;
      }
    }
    for (const match of round.matches) {
      if (match.outcome === null) {
        continue;
      }
      match.sides.forEach((side, index) => {
        const mine: Outcome = index === 0 ? "side_1" : "side_2";
        const theirs = membersOf(match.sides[index === 0 ? 1 : 0]);
        let difference = 0;
        for (const game of match.games) {
          if (game.score_1 !== null && game.score_2 !== null) {
            difference +=
              index === 0
                ? game.score_1 - game.score_2
                : game.score_2 - game.score_1;
          }
        }
        for (const entryId of membersOf(side)) {
          const row = rows.get(entryId);
          if (!row) {
            continue;
          }
          row.played += 1;
          row.score_difference += difference;
          row.points +=
            match.outcome === "draw"
              ? MATCH_POINTS.draw
              : match.outcome === mine
                ? MATCH_POINTS.win
                : MATCH_POINTS.loss;
          opponents.set(entryId, [
            ...(opponents.get(entryId) ?? []),
            ...theirs,
          ]);
        }
      });
    }
  }
  const pointsOf = (id: string) => rows.get(id)?.points ?? 0;
  for (const [id, row] of rows) {
    row.bh1 = (opponents.get(id) ?? []).reduce(
      (sum, o) => sum + pointsOf(o),
      0,
    );
  }
  for (const [id, row] of rows) {
    row.bh2 = (opponents.get(id) ?? []).reduce(
      (sum, o) => sum + (rows.get(o)?.bh1 ?? 0),
      0,
    );
  }
  const value = (row: Compared, key: SwissTiebreaker): number => {
    switch (key) {
      case "bh1":
        return row.bh1;
      case "bh2":
        return row.bh2;
      case "score_difference":
        return row.score_difference;
    }
  };
  const compare = (a: Compared, b: Compared): number => {
    if (a.points !== b.points) {
      return b.points - a.points;
    }
    for (const key of tiebreakers) {
      if (value(a, key) !== value(b, key)) {
        return value(b, key) - value(a, key);
      }
    }
    return 0;
  };
  const seedOf = new Map(
    mainEntries.map((entry) => [entry.id, entry.seed ?? 0]),
  );
  const ordered = [...rows.values()].sort(
    (a, b) =>
      compare(a, b) ||
      (seedOf.get(a.entry_id) ?? 0) - (seedOf.get(b.entry_id) ?? 0),
  );
  const ranked: SwissRankingRow[] = [];
  ordered.forEach((row, index) => {
    const previous = ordered[index - 1];
    const shared = previous !== undefined && compare(previous, row) === 0;
    ranked.push({
      ...row,
      place: shared ? (ranked[index - 1]?.place ?? index + 1) : index + 1,
    });
  });
  return { tiebreakers, qualifiers: group?.qualifiers ?? null, rows: ranked };
}

/** The group phase's order, whatever its format. */
function groupOrder(
  t: StoredTournament,
): { entry_id: string; place: number }[] {
  const group = groupPhase(t);
  if (!group) {
    return [];
  }
  if (group.format === "round_robin") {
    return roundRobinStandings(
      t.entries.filter((entry) => entry.stage === "main").map((e) => e.id),
      roundsOf(t, group),
      // BR-071: a round robin has no points for sitting out. The demo still
      // passes the stored value; PR #65 (closes #59) makes it null and drops this.
      group.sit_out_points ?? 0,
    ).map(({ entry_id, place }) => ({ entry_id, place }));
  }
  return rankingOf(t).rows.map(({ entry_id, place }) => ({ entry_id, place }));
}

// ---------------------------------------------------------------- places

function reasonOf(
  kind: PlaceReason["kind"],
  extra: Partial<PlaceReason> = {},
): PlaceReason {
  return {
    kind,
    round: null,
    score: null,
    opponent_entry_id: null,
    group_place: null,
    group_format: null,
    ...extra,
  };
}

/**
 * demo only: tournament places (BR-100–BR-104) with their reasons and the
 * placement points of the table (BR-110, BR-111). Before the tournament is
 * finished only the places already decided are listed. Returns undefined for
 * a tournament the base engine already handles (a plain round robin).
 */
export function placesOf(
  t: StoredTournament,
  table: readonly number[],
): PlacesRead | undefined {
  const group = groupPhase(t);
  const knockout = knockoutPhase(t);
  if (!knockout && group?.format === "round_robin") {
    return undefined;
  }
  const complete = t.state === "finished";
  const order = groupOrder(t);
  const groupReason = (place: number) =>
    reasonOf("group_place", {
      group_place: place,
      group_format: group?.format ?? null,
    });

  if (!knockout) {
    return {
      complete,
      rows: withPoints(
        order.map(({ entry_id, place }) => ({ place, entry_id })),
        table,
      ).map((row, i) => ({
        ...row,
        reason: groupReason(order[i]?.place ?? row.place),
      })),
    };
  }

  const rounds = roundsOf(t, knockout);
  const size = (rounds[0]?.matches.length ?? 2) * 2;
  const decided: { place: number; entry_id: string; reason: PlaceReason }[] =
    [];
  const thirdPlace = rounds.some((round) =>
    round.matches.some((m) => m.kind === "third_place"),
  );
  const roundTotal = rounds.length;
  const entryIds = new Set<string>();
  rounds.forEach((round, index) => {
    const name = roundName(index, roundTotal);
    const isFinal = index === roundTotal - 1;
    const format = (match: MatchRead) => formatOf(knockout, match, isFinal);
    for (const match of round.matches) {
      for (const side of match.sides) {
        if (index === 0 && side.entry_id !== null) {
          entryIds.add(side.entry_id);
        }
      }
      const winner = sideThat(match, "winner");
      const loser = sideThat(match, "loser");
      if (match.outcome === null || !winner || !loser) {
        continue;
      }
      const score = scoreOf(match, format(match));
      const flipped = score ? ([score[1], score[0]] as [number, number]) : null;
      const winnerScore = match.outcome === "side_1" ? score : flipped;
      const loserScore = match.outcome === "side_1" ? flipped : score;
      const winnerId = need(winner.entry_id);
      const loserId = need(loser.entry_id);
      if (isFinal && match.kind === "standard") {
        decided.push(
          {
            place: 1,
            entry_id: winnerId,
            reason: reasonOf("won_final", {
              score: winnerScore,
              opponent_entry_id: loserId,
            }),
          },
          {
            place: 2,
            entry_id: loserId,
            reason: reasonOf("lost_final", {
              score: loserScore,
              opponent_entry_id: winnerId,
            }),
          },
        );
      } else if (match.kind === "third_place") {
        decided.push(
          {
            place: 3,
            entry_id: winnerId,
            reason: reasonOf("won_third_place", {
              score: winnerScore,
              opponent_entry_id: loserId,
            }),
          },
          {
            place: 4,
            entry_id: loserId,
            reason: reasonOf("lost_third_place", {
              score: loserScore,
              opponent_entry_id: winnerId,
            }),
          },
        );
      } else if (!(thirdPlace && index === roundTotal - 2)) {
        // BR-102: those knocked out in the same round share the place after
        // everyone who is still in.
        decided.push({
          place: size / 2 ** (index + 1) + 1,
          entry_id: loserId,
          reason: reasonOf("lost_in_round", {
            round: name,
            score: loserScore,
            opponent_entry_id: winnerId,
          }),
        });
      }
    }
  });

  // BR-103: those who did not go through follow in their group-phase order.
  const knockoutPlayers = new Set(
    t.entries
      .filter((entry) => entryIds.has(entry.id))
      .flatMap((entry) => entry.player_ids),
  );
  const others = order.filter(({ entry_id }) => {
    const entry = t.entries.find((e) => e.id === entry_id);
    return (
      entry !== undefined &&
      !entry.player_ids.every((player) => knockoutPlayers.has(player))
    );
  });
  let previousGroupPlace = 0;
  let assigned = 0;
  others.forEach(({ entry_id, place }, index) => {
    if (place !== previousGroupPlace) {
      assigned = entryIds.size + index + 1;
      previousGroupPlace = place;
    }
    decided.push({ place: assigned, entry_id, reason: groupReason(place) });
  });

  decided.sort((a, b) => a.place - b.place);
  const withPts = withPoints(
    decided.map(({ place, entry_id }) => ({ place, entry_id })),
    table,
  );
  return {
    complete,
    rows: withPts.map((row, i): PlaceDetail => ({
      ...row,
      reason: decided[i]?.reason ?? reasonOf("group_place"),
    })),
  };
}

// ---------------------------------------------------------------- participants

export function participantsOf(t: StoredTournament): ParticipantRead[] {
  const group = groupPhase(t);
  const rounds = group ? roundsOf(t, group) : [];
  const latest = rounds[rounds.length - 1];
  return t.entries
    .filter((entry) => entry.stage === "main")
    .map((entry) => {
      const note = noteOf(t, entry.id);
      const sat = latest?.sitting_out.includes(entry.id) ?? false;
      return {
        entry_id: entry.id,
        state: entry.is_disabled ? "disabled" : sat ? "sat_out" : "playing",
        joined_round: note.joined_round,
        disabled_since_round: entry.is_disabled
          ? note.disabled_since_round
          : null,
        sat_out_round: sat ? (latest?.round_no ?? null) : null,
      };
    });
}

// ---------------------------------------------------------------- next round

function sitOutCounts(rounds: readonly RoundRead[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const round of rounds) {
    for (const id of round.sitting_out) {
      counts.set(id, (counts.get(id) ?? 0) + 1);
    }
  }
  return counts;
}

/**
 * BR-058, BR-063: who sits out. The fewest sit-outs first; then the lowest
 * placed (Swiss) or the lot (Monster DYP). Issue #24: not twice in a row.
 */
function chooseSitOuts(args: {
  ordered: readonly string[];
  count: number;
  rounds: readonly RoundRead[];
  exempt: ReadonlySet<string>;
  byLot: boolean;
  rng: () => number;
}): string[] {
  const { ordered, count, rounds, exempt, byLot, rng } = args;
  if (count === 0) {
    return [];
  }
  const counts = sitOutCounts(rounds);
  const lastRound = rounds[rounds.length - 1];
  const sort = (ids: readonly string[]) => {
    const lot = new Map(ids.map((id) => [id, rng()]));
    return [...ids].sort(
      (a, b) =>
        (counts.get(a) ?? 0) - (counts.get(b) ?? 0) ||
        (byLot
          ? (lot.get(a) ?? 0) - (lot.get(b) ?? 0)
          : ordered.indexOf(b) - ordered.indexOf(a)),
    );
  };
  let candidates = ordered.filter((id) => !exempt.has(id));
  if (rules.sitOuts === "fewest_sit_outs_not_twice_in_a_row") {
    const fresh = candidates.filter(
      (id) => !lastRound?.sitting_out.includes(id),
    );
    if (fresh.length >= count) {
      candidates = fresh;
    }
  }
  return sort(candidates).slice(0, count);
}

function playedBefore(rounds: readonly RoundRead[]) {
  const opponents = new Set<string>();
  const partners = new Set<string>();
  const key = (a: string, b: string) => [a, b].sort().join("|");
  for (const round of rounds) {
    for (const match of round.matches) {
      const [one, two] = match.sides;
      for (const a of one.player_ids) {
        for (const b of two.player_ids) {
          opponents.add(key(a, b));
        }
      }
      for (const side of match.sides) {
        if (side.player_ids.length === 2) {
          partners.add(key(need(side.player_ids[0]), need(side.player_ids[1])));
        }
      }
    }
  }
  return { opponents, partners, key };
}

export interface DrawnRound {
  matches: [MatchSideRead, MatchSideRead][];
  sitting_out: string[];
}

/**
 * demo only: the next round of a Swiss (BR-055–BR-058) or Monster DYP
 * (BR-060–BR-063), from the active entries and the current standings.
 */
export function drawNextRound(t: StoredTournament): DrawnRound {
  const group = groupPhase(t);
  if (!group) {
    return { matches: [], sitting_out: [] };
  }
  const rounds = roundsOf(t, group);
  const roundNo = rounds.length + 1;
  const rng = createRng(roundNo * 7919 + t.entries.length);
  const standing = rankingOf(t).rows.map((row) => row.entry_id);
  const seedOf = new Map(t.entries.map((entry) => [entry.id, entry.seed ?? 0]));
  const active = t.entries.filter((e) => e.stage === "main" && !e.is_disabled);
  const ordered =
    roundNo === 1
      ? active
          .map((e) => e.id)
          .sort((a, b) => (seedOf.get(a) ?? 0) - (seedOf.get(b) ?? 0))
      : standing.filter((id) => active.some((e) => e.id === id));
  const entryById = new Map(t.entries.map((e) => [e.id, e]));
  const side = (ids: string[]): MatchSideRead => ({
    entry_id: ids.length === 1 ? need(ids[0]) : null,
    player_ids: ids.flatMap((id) => entryById.get(id)?.player_ids ?? []),
    is_bye: false,
  });
  const history = playedBefore(rounds);

  if (group.format !== "monster_dyp") {
    const sitting = chooseSitOuts({
      ordered,
      count: ordered.length % 2,
      rounds,
      exempt: new Set(),
      byLot: false,
      rng,
    });
    const playing = ordered.filter((id) => !sitting.includes(id));
    if (roundNo === 1) {
      const half = playing.length / 2;
      return {
        matches: playing
          .slice(0, half)
          .map((id, i) => [side([id]), side([need(playing[half + i])])]),
        sitting_out: sitting,
      };
    }
    const left = [...playing];
    const matches: [MatchSideRead, MatchSideRead][] = [];
    while (left.length > 1) {
      const a = need(left.shift());
      const index = left.findIndex(
        (b) =>
          !history.opponents.has(
            history.key(
              entryById.get(a)?.player_ids[0] ?? a,
              entryById.get(b)?.player_ids[0] ?? b,
            ),
          ),
      );
      const [b] = left.splice(index === -1 ? 0 : index, 1);
      matches.push([side([a]), side([need(b)])]);
    }
    return { matches, sitting_out: sitting };
  }

  // Monster DYP.
  const groups = Math.floor(ordered.length / 4);
  const tops = new Set(
    roundNo <= 2 && rules.topPlayersSitOutExempt
      ? ordered.slice(0, groups)
      : [],
  );
  const sitting = chooseSitOuts({
    ordered,
    count: ordered.length - groups * 4,
    rounds,
    exempt: tops,
    byLot: true,
    rng,
  });
  const playing = ordered.filter((id) => !sitting.includes(id));
  const buckets: string[][] = [];
  if (roundNo <= 2) {
    // BR-061: the top players lead different groups.
    const leaders = playing.slice(0, groups);
    const rest = playing.slice(groups, groups * 4);
    leaders.forEach((leader, g) => {
      buckets.push([leader, ...rest.slice(g * 3, g * 3 + 3)]);
    });
  } else {
    for (let g = 0; g < groups; g++) {
      buckets.push(playing.slice(g * 4, g * 4 + 4));
    }
  }
  const matches = buckets.map(
    ([a, b, c, d]): [MatchSideRead, MatchSideRead] => {
      const players = (id: string | undefined) =>
        entryById.get(id ?? "")?.player_ids[0] ?? "";
      // BR-060: #1 + #4 v #2 + #3; BR-062: change the partners if they met.
      const options: [[string, string], [string, string]][] = [
        [
          [need(a), need(d)],
          [need(b), need(c)],
        ],
        [
          [need(a), need(c)],
          [need(b), need(d)],
        ],
        [
          [need(a), need(b)],
          [need(c), need(d)],
        ],
      ];
      const repeats = (option: (typeof options)[number]) =>
        option.filter(([p, q]) =>
          history.partners.has(history.key(players(p), players(q))),
        ).length;
      const best = options.reduce((x, y) => (repeats(y) < repeats(x) ? y : x));
      return [side(best[0]), side(best[1])];
    },
  );
  return { matches, sitting_out: sitting };
}

/** Builds the round the draw describes. */
export function roundFromDraw(args: {
  ids: Ids;
  phaseId: string;
  roundNo: number;
  drawn: DrawnRound;
}): RoundRead {
  const { ids, phaseId, roundNo, drawn } = args;
  const round: RoundRead = {
    id: ids(),
    phase_id: phaseId,
    round_no: roundNo,
    matches: [],
    sitting_out: drawn.sitting_out,
  };
  round.matches = drawn.matches.map(([one, two], index) => ({
    id: ids(),
    round_id: round.id,
    position: index + 1,
    kind: "standard",
    sides: [one, two],
    outcome: null,
    is_walkover: false,
    games: [],
    result_entered_at: null,
  }));
  return round;
}

// ---------------------------------------------------------------- knockout after the group phase

export interface PlannedEntry {
  seed: number;
  /** Group-phase entries (players) that form it. */
  member_ids: string[];
}

/**
 * demo only: the knockout's entries from the standings (BR-080–BR-085). The
 * disabled do not qualify (BR-080). `mode` null plays the entries as they are
 * (BR-085); the draw counter makes the lot repeatable.
 */
export function planKnockout(args: {
  t: StoredTournament;
  qualifiers: number;
  mode: MonsterKnockoutMode | null;
  draw: number;
}): { entries: PlannedEntry[]; skipped: string[]; qualifiers: number } {
  const { t, mode, draw } = args;
  const ranking = rankingOf(t).rows;
  const active = ranking.filter((row) => !row.is_disabled);
  const paired =
    mode === "seeded_pairs" ||
    mode === "a_little_mercy" ||
    mode === "lord_have_mercy";
  let count = Math.min(Math.max(args.qualifiers, 2), active.length);
  if (paired && count % 2 === 1) {
    count -= 1;
  }
  const chosen = active.slice(0, count).map((row) => row.entry_id);
  const cut = ranking.slice(0, count).filter((row) => row.is_disabled);
  const skipped = cut.map((row) => row.entry_id);
  const rng = createRng(draw * 104729 + count);
  const half = count / 2;
  const top = chosen.slice(0, half);
  const bottom = chosen.slice(half);
  let entries: PlannedEntry[];
  switch (mode) {
    case "seeded_pairs":
      entries = top.map((id, i) => ({
        seed: i + 1,
        member_ids: [id, need(bottom[i])],
      }));
      break;
    case "a_little_mercy": {
      const partners = shuffled(bottom, rng);
      entries = top.map((id, i) => ({
        seed: i + 1,
        member_ids: [id, need(partners[i])],
      }));
      break;
    }
    case "lord_have_mercy": {
      const mixed = shuffled(chosen, rng);
      entries = Array.from({ length: half }, (_, i) => ({
        seed: i + 1,
        member_ids: [need(mixed[2 * i]), need(mixed[2 * i + 1])],
      }));
      break;
    }
    case "singles":
    case null:
      entries = chosen.map((id, i) => ({ seed: i + 1, member_ids: [id] }));
      break;
  }
  return { entries, skipped, qualifiers: count };
}

export function previewOf(args: {
  t: StoredTournament;
  qualifiers: number;
  mode: MonsterKnockoutMode | null;
  draw: number;
}): KnockoutPreview {
  const { t } = args;
  const plan = planKnockout(args);
  const places = new Map(
    rankingOf(t).rows.map((row) => [row.entry_id, row.place]),
  );
  const size = bracketSize(plan.entries.length);
  const slots = seedSlots(size);
  const group = groupPhase(t);
  return {
    max_qualifiers: t.entries.filter(
      (e) => e.stage === "main" && !e.is_disabled,
    ).length,
    qualifiers: plan.qualifiers,
    entries: plan.entries.map((entry) => ({
      seed: entry.seed,
      members: entry.member_ids.map((id) => ({
        entry_id: id,
        place: places.get(id) ?? 0,
      })),
    })),
    first_round: Array.from(
      { length: size / 2 },
      (_, j): [number, number | null] => {
        const a = slots[2 * j] ?? 0;
        const b = slots[2 * j + 1] ?? 0;
        return [
          a > plan.entries.length ? b : a,
          a > plan.entries.length || b > plan.entries.length ? null : b,
        ];
      },
    ),
    bracket_size: size,
    locks_round_no: group ? roundsOf(t, group).length : 0,
    skipped_entry_ids: plan.skipped,
  };
}
