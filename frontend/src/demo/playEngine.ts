// demo only, the engine decides
//
// Stand-ins for the engine and the services behind the play screens
// (screens 6–8): field placements, the waiting order, result checks and the
// live round-robin standings. They follow PRD.md §7.10–§7.16 loosely and
// src/lib/rules.ts for the rules still open; none of this is the real
// behaviour (ADR-009).
import { newId } from "@/lib/newId";
import { MATCH_POINTS, rules } from "@/lib/rules";

import type {
  ErrorResponse,
  FieldRead,
  FormResult,
  MatchFormat,
  MatchRead,
  PhaseRead,
  PlacementsWrite,
  PlayRead,
  PlayStandingRow,
  ResultWrite,
  Side,
  TournamentStandingRow,
} from "./contract";
import { fillFields, gameDifference } from "./engine";
import type { StoredTournament } from "./seed";
import { tournamentStandings } from "./store";

/** A refusal with the API's code, answered as 404, 409 or 422 (ADR-008). */
export interface PlayRefusal {
  status: 404 | 409 | 422;
  code: ErrorResponse["code"];
  detail: Record<string, string | number | string[] | null>;
}

// DATA-MODEL §4.5 `requeued_at`: a match whose field was removed waits ahead
// of the schedule order, earliest first (BR-132). Kept beside the store,
// keyed by the stored match, so a reset of the store forgets it.
const requeuedAt = new WeakMap<MatchRead, number>();
let requeueClock = 0;

function playerIds(match: MatchRead): string[] {
  return match.sides.flatMap((side) => side.player_ids);
}

function sidesKnown(match: MatchRead): boolean {
  return match.sides.every(
    (side) => !side.is_bye && side.player_ids.length > 0,
  );
}

/** Every match in schedule order: by phase, round and position (BR-130). */
export function scheduleOrder(t: StoredTournament): MatchRead[] {
  const phasePosition = new Map(t.phases.map((p) => [p.id, p.position]));
  return [...t.rounds]
    .sort(
      (a, b) =>
        (phasePosition.get(a.phase_id) ?? 0) -
          (phasePosition.get(b.phase_id) ?? 0) || a.round_no - b.round_no,
    )
    .flatMap((round) =>
      [...round.matches].sort((a, b) => a.position - b.position),
    );
}

export function findMatch(
  t: StoredTournament,
  matchId: string,
): MatchRead | undefined {
  return t.rounds.flatMap((r) => r.matches).find((m) => m.id === matchId);
}

export function phaseOf(
  t: StoredTournament,
  match: MatchRead,
): PhaseRead | undefined {
  const round = t.rounds.find((r) => r.id === match.round_id);
  return t.phases.find((p) => p.id === round?.phase_id);
}

/**
 * The waiting list (FR-092, DATA-MODEL §4.6): no result, not on a field,
 * both sides known; requeued matches first, earliest first, then schedule
 * order.
 */
export function waitingOrder(t: StoredTournament): MatchRead[] {
  const onField = new Set(t.fields.map((field) => field.match_id));
  const schedule = scheduleOrder(t).filter(
    (match) =>
      match.outcome === null && !onField.has(match.id) && sidesKnown(match),
  );
  const requeued = schedule
    .filter((match) => requeuedAt.has(match))
    .sort((a, b) => (requeuedAt.get(a) ?? 0) - (requeuedAt.get(b) ?? 0));
  return [...requeued, ...schedule.filter((match) => !requeuedAt.has(match))];
}

/**
 * Fills the free fields, lowest number first, with the first waiting match
 * whose players are on no field (BR-130, BR-131). `except` keeps matches out
 * of this fill, such as one just taken off its field (FR-093).
 */
export function fill(t: StoredTournament, except: readonly string[] = []) {
  const matchesById = new Map(
    t.rounds.flatMap((r) => r.matches).map((m) => [m.id, m]),
  );
  t.fields = fillFields(
    t.fields,
    waitingOrder(t).filter((match) => !except.includes(match.id)),
    matchesById,
  );
  for (const field of t.fields) {
    const match =
      field.match_id === null ? undefined : matchesById.get(field.match_id);
    if (match) {
      requeuedAt.delete(match);
    }
  }
}

/**
 * Players who would be on two fields at once, with the fields that would
 * hold them, lowest number first (BR-131).
 */
function doubleBooked(
  t: StoredTournament,
  fields: readonly FieldRead[],
): { playerIds: string[]; fieldIds: string[] } {
  const on = new Map<string, FieldRead[]>();
  for (const field of fields) {
    const match =
      field.match_id === null ? undefined : findMatch(t, field.match_id);
    for (const player of match ? playerIds(match) : []) {
      on.set(player, [...(on.get(player) ?? []), field]);
    }
  }
  const twice = [...on].filter(([, held]) => held.length > 1);
  const involved = new Map(
    twice.flatMap(([, held]) => held.map((f) => [f.id, f] as const)),
  );
  return {
    playerIds: twice.map(([player]) => player).toSorted(),
    fieldIds: [...involved.values()]
      .toSorted((a, b) => a.number - b.number)
      .map((f) => f.id),
  };
}

/**
 * The four operations of FR-093: a waiting match on a free field, a match
 * to a free field, a match back to waiting, a swap of two matches that are
 * both on fields. Replacing and rotating are not allowed (ADR-008).
 */
function isAllowed(placements: PlacementsWrite["placements"]): boolean {
  const [first, second] = placements;
  if (first === undefined) {
    return false;
  }
  if (second === undefined) {
    return first.field_id !== first.from_field_id;
  }
  return (
    first.from_field_id !== null &&
    second.from_field_id !== null &&
    first.field_id === second.from_field_id &&
    second.field_id === first.from_field_id
  );
}

/**
 * Places, moves, swaps or takes off matches as the request states (FR-093,
 * BR-133). Refuses a match with a result or an unknown side (BR-091), a
 * match that is not on the field the screen saw it on, a field another
 * match keeps, anything but the operations of FR-093, and any player on two
 * fields (BR-131).
 */
export function place(
  t: StoredTournament,
  { placements }: PlacementsWrite,
): PlayRefusal | null {
  const moved = new Set(placements.map((p) => p.match_id));
  const targets = placements.flatMap((p) =>
    p.field_id === null ? [] : [p.field_id],
  );
  if (new Set(targets).size !== targets.length) {
    return { status: 422, code: "validation_failed", detail: {} };
  }
  const fields = t.fields.map((field) => ({
    ...field,
    match_id:
      field.match_id !== null && moved.has(field.match_id)
        ? null
        : field.match_id,
  }));
  for (const { match_id, field_id, from_field_id } of placements) {
    const match = findMatch(t, match_id);
    if (!match) {
      return { status: 404, code: "match_not_found", detail: {} };
    }
    if (match.outcome !== null) {
      return { status: 409, code: "match_has_result", detail: { match_id } };
    }
    if (!sidesKnown(match)) {
      return { status: 422, code: "match_sides_unknown", detail: {} };
    }
    const seenOn = t.fields.find((f) => f.match_id === match_id)?.id ?? null;
    if (seenOn !== from_field_id) {
      return { status: 409, code: "placement_changed", detail: {} };
    }
    if (field_id === null) {
      continue;
    }
    const field = fields.find((f) => f.id === field_id);
    if (!field) {
      return { status: 404, code: "field_not_found", detail: {} };
    }
    if (field.match_id !== null) {
      // A swap names both matches; a field kept by another match is stale.
      return {
        status: 409,
        code: "field_not_free",
        detail: { field_id, match_id: field.match_id },
      };
    }
    field.match_id = match_id;
  }
  if (!isAllowed(placements)) {
    return { status: 422, code: "placement_not_allowed", detail: {} };
  }
  const twice = doubleBooked(t, fields);
  if (twice.playerIds.length > 0) {
    return {
      status: 422,
      code: "player_on_another_field",
      detail: { player_ids: twice.playerIds, field_ids: twice.fieldIds },
    };
  }
  t.fields = fields;
  const toWaiting = placements
    .filter((p) => p.field_id === null)
    .map((p) => p.match_id);
  for (const matchId of moved) {
    const match = findMatch(t, matchId);
    if (match) {
      requeuedAt.delete(match);
    }
  }
  fill(t, toWaiting);
  return null;
}

/** The number a new field gets: the lowest free one (BR-132). */
export function nextFieldNumber(t: StoredTournament): number {
  const taken = new Set(t.fields.map((field) => field.number));
  let number = 1;
  while (taken.has(number)) {
    number += 1;
  }
  return number;
}

/** Adds a field, which takes the next waiting match (FR-090, BR-132). */
export function addField(
  t: StoredTournament,
  number: number,
): FieldRead | PlayRefusal {
  const expected = nextFieldNumber(t);
  if (number !== expected) {
    return {
      status: 409,
      code: "field_number_changed",
      detail: { number: expected },
    };
  }
  const field: FieldRead = { id: newId(), number, match_id: null };
  t.fields = [...t.fields, field].sort((a, b) => a.number - b.number);
  fill(t);
  return t.fields.find((f) => f.id === field.id) ?? field;
}

/**
 * Removes a field; its match goes to the front of the waiting list and the
 * other fields keep their numbers. The last field stays (BR-132).
 */
export function removeField(
  t: StoredTournament,
  fieldId: string,
): PlayRefusal | null {
  const field = t.fields.find((f) => f.id === fieldId);
  if (!field) {
    return { status: 404, code: "field_not_found", detail: {} };
  }
  if (t.fields.length === 1) {
    return { status: 422, code: "last_field", detail: {} };
  }
  const match =
    field.match_id === null ? undefined : findMatch(t, field.match_id);
  if (match) {
    requeueClock += 1;
    requeuedAt.set(match, requeueClock);
  }
  t.fields = t.fields.filter((f) => f.id !== fieldId);
  fill(t);
  return null;
}

/** The format a match plays: the final may have its own (BR-120). */
export function formatOf(t: StoredTournament, match: MatchRead): MatchFormat {
  const phase = phaseOf(t, match);
  if (!phase) {
    return "bo1";
  }
  if (phase.kind === "knockout" && phase.final_match_format !== null) {
    const rounds = t.rounds.filter((r) => r.phase_id === phase.id);
    const last = rounds.at(-1);
    if (last?.id === match.round_id && match.kind === "standard") {
      return phase.final_match_format;
    }
  }
  return phase.match_format;
}

/** Whether every game needs its score (BR-092, rules.gameScoresRequired). */
export function scoresRequired(phase: PhaseRead): boolean {
  switch (rules.gameScoresRequired) {
    case "swiss_and_monster_dyp":
      return phase.format === "swiss" || phase.format === "monster_dyp";
    case "when_score_difference_counts":
      return phase.kind === "group" && phase.format === "round_robin"
        ? rules.roundRobinTiebreakers.includes("score_difference")
        : (phase.tiebreakers ?? []).includes("score_difference");
  }
}

const GAMES_TO_WIN = { bo1: 1, bo2: 2, bo3: 2, bo5: 3 } as const;

/** Why the backend would refuse a result: its 422 code and detail (ADR-008). */
export interface ResultRefusal {
  code: ErrorResponse["code"];
  detail: Record<string, string | number>;
}

/**
 * Checks a whole result against the format, the draw rule and the scores
 * (BR-090, BR-092, BR-121, BR-124) with the backend's codes; null when it
 * may be saved.
 */
export function checkResult(
  body: ResultWrite,
  format: MatchFormat,
  phase: PhaseRead,
  drawsAllowed: boolean,
): ResultRefusal | null {
  if (body.walkover_winner !== null) {
    return body.games.length === 0
      ? null
      : { code: "validation_failed", detail: { rule: "BR-124" } };
  }
  const unfit: ResultRefusal = {
    code: "result_does_not_fit_format",
    detail: { format, games: body.games.length },
  };
  const drawAllowed = phase.kind === "group" && drawsAllowed;
  const wins = { side_1: 0, side_2: 0 };
  for (const [index, game] of body.games.entries()) {
    const { score_1: a, score_2: b } = game;
    const gameNo = { game_no: index + 1 };
    if (a !== null && b !== null) {
      const agrees =
        game.winner === "draw"
          ? a === b
          : game.winner === "side_1"
            ? a > b
            : b > a;
      if (!agrees) {
        return { code: "game_score_mismatch", detail: gameNo };
      }
    } else if (a !== null || b !== null) {
      return { code: "game_score_mismatch", detail: gameNo };
    } else if (scoresRequired(phase)) {
      return { code: "scores_required", detail: gameNo };
    }
  }
  for (const game of body.games) {
    if (game.winner === "draw") {
      if (format !== "bo1") {
        return unfit;
      }
      continue;
    }
    if (
      format !== "bo2" &&
      Math.max(wins.side_1, wins.side_2) >= GAMES_TO_WIN[format]
    ) {
      return unfit;
    }
    wins[game.winner] += 1;
  }
  const played = body.games.length;
  const draw = { code: "draws_not_allowed", detail: {} } as const;
  switch (format) {
    case "bo1":
      if (played !== 1) {
        return unfit;
      }
      return body.games[0]?.winner === "draw" && !drawAllowed ? draw : null;
    case "bo2":
      if (played !== 2) {
        return unfit;
      }
      return wins.side_1 === wins.side_2 && !drawAllowed ? draw : null;
    case "bo3":
    case "bo5":
      return Math.max(wins.side_1, wins.side_2) === GAMES_TO_WIN[format]
        ? null
        : unfit;
  }
}

type Outcome = NonNullable<MatchRead["outcome"]>;

/** The outcome a checked result makes: the walkover's winner, else the games' majority. */
function outcomeOf(body: ResultWrite): Outcome {
  if (body.walkover_winner !== null) {
    return body.walkover_winner;
  }
  const wins = { side_1: 0, side_2: 0, draw: 0 };
  for (const game of body.games) {
    wins[game.winner] += 1;
  }
  return wins.side_1 > wins.side_2
    ? "side_1"
    : wins.side_2 > wins.side_1
      ? "side_2"
      : "draw";
}

/** The backend's `_same_result`: the stored outcome, walkover and games equal the sent ones. */
function sameResult(
  match: MatchRead,
  body: ResultWrite,
  outcome: Outcome,
): boolean {
  return (
    match.outcome === outcome &&
    match.is_walkover === (body.walkover_winner !== null) &&
    match.games.length === body.games.length &&
    match.games.every((stored, i) => {
      const sent = body.games[i];
      return (
        stored.winner === sent?.winner &&
        stored.score_1 === sent.score_1 &&
        stored.score_2 === sent.score_2
      );
    })
  );
}

/**
 * Writes a checked result, or clears it when the body is empty (FR-053), as
 * the backend does. A result equal to the stored one changes nothing, the time
 * included. A new one frees the match's field, which takes the next match
 * (FR-094). Clearing a match without a result changes nothing; clearing one
 * with a result leaves it waiting in schedule order, not put back on its
 * field, and the free fields are filled (BR-134, BR-130). It reopens a
 * finished tournament (BR-095).
 */
export function writeResult(
  t: StoredTournament,
  match: MatchRead,
  body: ResultWrite,
): void {
  if (body.walkover_winner === null && body.games.length === 0) {
    if (match.outcome === null) {
      return;
    }
    match.outcome = null;
    match.is_walkover = false;
    match.games = [];
    match.result_entered_at = null;
    if (t.state === "finished") {
      t.state = "in_progress";
    }
    fill(t);
    return;
  }
  const outcome = outcomeOf(body);
  if (sameResult(match, body, outcome)) {
    return;
  }
  requeuedAt.delete(match);
  match.is_walkover = body.walkover_winner !== null;
  match.games = body.games.map((game, i) => ({ game_no: i + 1, ...game }));
  match.outcome = outcome;
  match.result_entered_at = new Date().toISOString();
  t.fields = t.fields.map((field) =>
    field.match_id === match.id ? { ...field, match_id: null } : field,
  );
  fill(t);
}

function groupMatches(t: StoredTournament): MatchRead[] {
  const group = t.phases.find((phase) => phase.kind === "group");
  return scheduleOrder(t).filter(
    (match) => phaseOf(t, match)?.id === group?.id && sidesKnown(match),
  );
}

/** Group-phase matches without a result (FR-040). */
export function groupMatchesLeft(t: StoredTournament): number {
  return groupMatches(t).filter((m) => m.outcome === null).length;
}

/** Every group-phase match has a result (FR-040). */
export function groupDone(t: StoredTournament): boolean {
  const matches = groupMatches(t);
  return matches.length > 0 && matches.every((m) => m.outcome !== null);
}

/** A round robin's results lock once the knockout is drawn (BR-053). */
export function groupLocked(t: StoredTournament, match: MatchRead): boolean {
  return (
    phaseOf(t, match)?.kind === "group" &&
    t.phases.some((phase) => phase.kind === "knockout")
  );
}

/** The entries a side stands for: its entry, or its players' own entries (Monster DYP). */
function sideEntries(t: StoredTournament, side: MatchRead["sides"][number]) {
  if (side.entry_id !== null) {
    return [side.entry_id];
  }
  return t.entries
    .filter(
      (entry) =>
        entry.stage === "main" &&
        entry.player_ids.some((id) => side.player_ids.includes(id)),
    )
    .map((entry) => entry.id);
}

function form(t: StoredTournament, entryId: string): FormResult[] {
  return groupMatches(t)
    .flatMap((m): FormResult[] => {
      const index = m.sides.findIndex((side) =>
        sideEntries(t, side).includes(entryId),
      );
      if (m.outcome === null || index === -1) {
        return [];
      }
      const mine: Side = index === 0 ? "side_1" : "side_2";
      return [
        m.outcome === "draw" ? "drawn" : m.outcome === mine ? "won" : "lost",
      ];
    })
    .slice(-5);
}

type SwissRow = Omit<PlayStandingRow, "place" | "form" | "ahead_by"> & {
  opponents: string[];
};

/**
 * Swiss and Monster DYP standings, simply (BR-070–BR-073): points, then the
 * phase's tie-breakers (FR-043, rules.swissTiebreakers by default); entries
 * still level share the place (BR-074).
 */
function swissStandings(
  t: StoredTournament,
  group: PhaseRead,
): Omit<PlayStandingRow, "form" | "ahead_by">[] {
  // BR-076, BR-077: each entry or player who sits out gets them, as points.
  const sitOutPoints = group.sit_out_points ?? 0;
  const rows = new Map<string, SwissRow>(
    t.entries
      .filter((entry) => entry.stage === "main")
      .map((entry) => [
        entry.id,
        {
          entry_id: entry.id,
          played: 0,
          won: 0,
          drawn: 0,
          lost: 0,
          sat_out: 0,
          points: 0,
          game_difference: 0,
          score_difference: 0,
          bh1: 0,
          bh2: 0,
          opponents: [],
        },
      ]),
  );
  for (const round of t.rounds.filter((r) => r.phase_id === group.id)) {
    for (const id of round.sitting_out) {
      const row = rows.get(id);
      if (row) {
        row.sat_out += 1;
        row.points += sitOutPoints;
      }
    }
    for (const match of round.matches) {
      if (match.outcome === null) {
        continue;
      }
      const sides = match.sides.map((side) => sideEntries(t, side));
      sides.forEach((ids, index) => {
        const mine: Side = index === 0 ? "side_1" : "side_2";
        const others = sides[index === 0 ? 1 : 0] ?? [];
        const games = gameDifference(
          match,
          index === 0 ? 0 : 1,
          group.match_format,
        );
        let difference = 0;
        for (const game of match.games) {
          if (game.score_1 !== null && game.score_2 !== null) {
            difference +=
              index === 0
                ? game.score_1 - game.score_2
                : game.score_2 - game.score_1;
          }
        }
        for (const id of ids) {
          const row = rows.get(id);
          if (!row) {
            continue;
          }
          row.played += 1;
          row.game_difference += games;
          row.score_difference += difference;
          row.opponents.push(...others);
          if (match.outcome === "draw") {
            row.drawn += 1;
            row.points += MATCH_POINTS.draw;
          } else if (match.outcome === mine) {
            row.won += 1;
            row.points += MATCH_POINTS.win;
          } else {
            row.lost += 1;
          }
        }
      });
    }
  }
  const points = (id: string) => rows.get(id)?.points ?? 0;
  for (const row of rows.values()) {
    row.bh1 = row.opponents.reduce((sum, id) => sum + points(id), 0);
  }
  for (const row of rows.values()) {
    row.bh2 = row.opponents.reduce(
      (sum, id) => sum + (rows.get(id)?.bh1 ?? 0),
      0,
    );
  }
  const tiebreakers = group.tiebreakers ?? rules.swissTiebreakers;
  const compare = (a: SwissRow, b: SwissRow): number => {
    if (a.points !== b.points) {
      return b.points - a.points;
    }
    for (const tiebreaker of tiebreakers) {
      const value = (row: SwissRow) =>
        tiebreaker === "bh1"
          ? (row.bh1 ?? 0)
          : tiebreaker === "bh2"
            ? (row.bh2 ?? 0)
            : row.score_difference;
      if (value(a) !== value(b)) {
        return value(b) - value(a);
      }
    }
    return 0;
  };
  const sorted = [...rows.values()].sort(compare);
  const places: number[] = [];
  return sorted.map((row, index) => {
    const above = sorted[index - 1];
    const level = above !== undefined && compare(above, row) === 0;
    const place = level ? (places[index - 1] ?? index + 1) : index + 1;
    places.push(place);
    return {
      place,
      entry_id: row.entry_id,
      played: row.played,
      won: row.won,
      drawn: row.drawn,
      lost: row.lost,
      sat_out: row.sat_out,
      points: row.points,
      game_difference: row.game_difference,
      score_difference: row.score_difference,
      bh1: row.bh1,
      bh2: row.bh2,
    };
  });
}

function headToHead(t: StoredTournament, a: string, b: string): number {
  let points = 0;
  for (const m of groupMatches(t)) {
    const ids = m.sides.map((side) => side.entry_id);
    if (m.outcome !== null && ids.includes(a) && ids.includes(b)) {
      const aSide: Side = ids[0] === a ? "side_1" : "side_2";
      points += m.outcome === aSide ? 1 : m.outcome === "draw" ? 0 : -1;
    }
  }
  return points;
}

/** The tie-breaker of rules.roundRobinTiebreakers that ranks `row` above `next` (BR-101). */
function aheadBy(
  t: StoredTournament,
  rows: readonly TournamentStandingRow[],
  row: TournamentStandingRow,
  next: TournamentStandingRow | undefined,
): PlayStandingRow["ahead_by"] {
  if (next?.points !== row.points || next.place === row.place) {
    return null;
  }
  const level = rows.filter((other) => other.points === row.points).length;
  for (const tiebreaker of rules.roundRobinTiebreakers) {
    switch (tiebreaker) {
      case "head_to_head":
        if (level === 2 && headToHead(t, row.entry_id, next.entry_id) > 0) {
          return tiebreaker;
        }
        break;
      case "score_difference":
        if (row.score_difference > next.score_difference) {
          return tiebreaker;
        }
        break;
      case "game_difference":
        if (row.game_difference > next.game_difference) {
          return tiebreaker;
        }
        break;
    }
  }
  return null;
}

/** The play screens' read: waiting order, live standings, phase end (FR-060, FR-092). */
export function playRead(t: StoredTournament): PlayRead {
  const busyFields = t.fields.flatMap((field) => {
    const match =
      field.match_id === null ? undefined : findMatch(t, field.match_id);
    return match ? [{ field_id: field.id, players: playerIds(match) }] : [];
  });
  const group = t.phases.find((phase) => phase.kind === "group");
  const swiss =
    group?.format === "swiss" || group?.format === "monster_dyp"
      ? group
      : undefined;
  const rows = swiss ? [] : tournamentStandings(t);
  const standings: PlayStandingRow[] =
    swiss === undefined
      ? rows.map((row, i) => ({
          ...row,
          form: form(t, row.entry_id),
          ahead_by: aheadBy(t, rows, row, rows[i + 1]),
          bh1: null,
          bh2: null,
        }))
      : swissStandings(t, swiss).map((row) => ({
          ...row,
          form: form(t, row.entry_id),
          ahead_by: null,
        }));
  return {
    waiting: waitingOrder(t).map((match) => {
      const players = new Set(playerIds(match));
      return {
        match_id: match.id,
        busy: busyFields.flatMap(({ field_id, players: onField }) => {
          const player_ids = onField.filter((p) => players.has(p));
          return player_ids.length > 0 ? [{ field_id, player_ids }] : [];
        }),
      };
    }),
    standings,
    group_done: groupDone(t),
  };
}
