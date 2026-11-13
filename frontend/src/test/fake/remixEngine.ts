// demo only, the engine decides
//
// Stand-in for the Lord have mercy knockout of the backend (BR-084, BR-140 to
// BR-146, ADR-009): the pairs change every round, so the knockout starts with
// round 1 only and the organizer draws each next round once the round before
// is complete. Minimal: the draw is a seeded shuffle per round number, so the
// same round always gives the same pairs; tests assert structure, not pairs.
import type {
  MatchRead,
  MatchSideRead,
  PlaceDetail,
  PlaceReason,
  PlacesRead,
  PublicRemixRead,
  RemixMatch,
  RemixRead,
  RemixRound,
  RemixSide,
  RoundRead,
} from "./contract";
import { createRng, splitPlacementPoints } from "./engine";
import {
  formatOf,
  groupPhase,
  knockoutPhase,
  need,
  rankingOf,
  reasonOf,
  roundsOf,
  scoreOf,
  shuffled,
} from "./finalsEngine";
import type { StoredTournament } from "./seed";

type Ids = () => string;
type Outcome = NonNullable<MatchRead["outcome"]>;
type RoundName = RemixRound["name"];

const MODE = "lord_have_mercy";

/** BR-084: the knockout is a Lord have mercy one. */
export function isRemix(t: StoredTournament): boolean {
  return knockoutPhase(t)?.monster_knockout_mode === MODE;
}

/** The rounds drawn so far, round 1 first. */
export function remixRounds(t: StoredTournament): RoundRead[] {
  const phase = knockoutPhase(t);
  return phase ? roundsOf(t, phase) : [];
}

/** How many rounds the knockout will have: log2 of twice the round-1 matches. */
export function remixRoundCount(t: StoredTournament): number {
  const first = remixRounds(t)[0];
  const matches = first?.matches.filter((m) => m.kind === "standard").length;
  return matches === undefined ? 0 : Math.log2(matches * 2);
}

const isBye = (match: MatchRead): boolean =>
  match.sides.some((side) => side.is_bye);

/** BR-140: a match is decided by its result, or by a bye. */
const isDecided = (match: MatchRead): boolean =>
  isBye(match) || match.outcome !== null;

const inOrder = (round: RoundRead): MatchRead[] =>
  [...round.matches].sort((a, b) => a.position - b.position);

/** The pair that went through: the result's winner, or the pair against a bye. */
function winnerOf(match: MatchRead): MatchSideRead | null {
  const [one, two] = match.sides;
  if (one.is_bye || two.is_bye) {
    return one.is_bye ? (two.is_bye ? null : two) : one;
  }
  if (match.outcome === "side_1") {
    return one;
  }
  return match.outcome === "side_2" ? two : null;
}

function loserOf(match: MatchRead): MatchSideRead | null {
  const [one, two] = match.sides;
  if (isBye(match) || match.outcome === null || match.outcome === "draw") {
    return null;
  }
  return match.outcome === "side_1" ? two : one;
}

const playersOf = (side: MatchSideRead | null): string[] =>
  side ? side.player_ids : [];

function standardLosers(round: RoundRead | undefined): string[] {
  return (round?.matches ?? [])
    .filter((match) => match.kind === "standard")
    .flatMap((match) => playersOf(loserOf(match)));
}

/** BR-140: the organizer can draw the next round. */
export function canDrawNext(t: StoredTournament): boolean {
  const rounds = remixRounds(t);
  const newest = rounds.at(-1);
  return (
    t.state === "in_progress" &&
    newest !== undefined &&
    rounds.length < remixRoundCount(t) &&
    newest.matches.every(isDecided)
  );
}

/** How many matches of the newest round still lack a result (BR-140). */
export function remixMatchesLeft(t: StoredTournament): number {
  const newest = remixRounds(t).at(-1);
  return (newest?.matches ?? []).filter(
    (match) => !isBye(match) && match.outcome === null,
  ).length;
}

function pairsOf(players: readonly string[]): string[][] {
  const pairs: string[][] = [];
  for (let i = 0; i + 1 < players.length; i += 2) {
    pairs.push([need(players[i]), need(players[i + 1])]);
  }
  return pairs;
}

const side = (players: readonly string[]): MatchSideRead => ({
  entry_id: null,
  player_ids: [...players],
  is_bye: false,
});

function matchOf(args: {
  ids: Ids;
  roundId: string;
  position: number;
  kind: MatchRead["kind"];
  sides: [string[], string[]];
}): MatchRead {
  return {
    id: args.ids(),
    round_id: args.roundId,
    position: args.position,
    kind: args.kind,
    sides: [side(args.sides[0]), side(args.sides[1])],
    outcome: null,
    is_walkover: false,
    games: [],
    result_entered_at: null,
  };
}

/**
 * BR-141 to BR-144, BR-156: draws the next round from the players who went
 * through, by a seeded shuffle of the round number: players 1 and 2 form the
 * first pair, 3 and 4 the second, and pairs 1 and 2 play the first match. The
 * final's round also gets the third-place match between the semifinal losers.
 * The caller has checked that the round can be drawn.
 */
export function drawRemixRound(t: StoredTournament, ids: Ids): RoundRead {
  const phase = need(knockoutPhase(t));
  const rounds = remixRounds(t);
  const newest = need(rounds.at(-1));
  const roundNo = rounds.length + 1;
  const through = newest.matches
    .filter((match) => match.kind === "standard")
    .flatMap((match) => playersOf(winnerOf(match)))
    .sort();
  const teams = pairsOf(shuffled(through, createRng(roundNo * 7919 + 11)));
  const round: RoundRead = {
    id: ids(),
    phase_id: phase.id,
    round_no: roundNo,
    matches: [],
    sitting_out: [],
  };
  for (let i = 0; i + 1 < teams.length; i += 2) {
    round.matches.push(
      matchOf({
        ids,
        roundId: round.id,
        position: i / 2 + 1,
        kind: "standard",
        sides: [need(teams[i]), need(teams[i + 1])],
      }),
    );
  }
  if (phase.third_place_match && roundNo === remixRoundCount(t)) {
    const [first, second] = pairsOf(
      shuffled(
        standardLosers(rounds.at(-1)).sort(),
        createRng(roundNo * 104729 + 13),
      ),
    );
    round.matches.push(
      matchOf({
        ids,
        roundId: round.id,
        position: round.matches.length + 1,
        kind: "third_place",
        sides: [need(first), need(second)],
      }),
    );
  }
  t.rounds.push(round);
  return round;
}

/**
 * FR-037: the tournament is finished once every round is drawn and every
 * match of the last one has a result; clearing a result or deleting a round
 * reopens it (BR-095).
 */
export function syncRemix(t: StoredTournament): void {
  const rounds = remixRounds(t);
  const last = rounds.at(-1);
  const done =
    last !== undefined &&
    rounds.length === remixRoundCount(t) &&
    last.matches.every((match) => match.outcome !== null);
  if (done && t.state === "in_progress") {
    t.state = "finished";
  } else if (!done && t.state === "finished") {
    t.state = "in_progress";
  }
}

/**
 * BR-146: drawing a round locks the winners of the round before. A result
 * there can be corrected with the same winner (`outcome`), never cleared
 * (null) and never given to the other pair.
 */
export function remixLocked(
  t: StoredTournament,
  match: MatchRead,
  outcome: Outcome | null,
): boolean {
  const rounds = remixRounds(t);
  const round = rounds.find((r) => r.id === match.round_id);
  return (
    round !== undefined &&
    round.id !== rounds.at(-1)?.id &&
    outcome !== match.outcome
  );
}

/** BR-147: the players still in, whose latest pair won, had a bye or has no result yet. */
function playersStillIn(t: StoredTournament): Set<string> {
  const rounds = remixRounds(t);
  const count = remixRoundCount(t);
  const latest = new Map<string, MatchRead>();
  for (const round of rounds) {
    for (const match of inOrder(round)) {
      for (const player of match.sides.flatMap((s) => s.player_ids)) {
        latest.set(player, match);
      }
    }
  }
  const waiting = new Set(
    need(knockoutPhase(t)).third_place_match && rounds.length < count
      ? standardLosers(rounds[count - 2])
      : [],
  );
  return new Set(
    [...latest]
      .filter(
        ([player, match]) =>
          match.outcome === null ||
          playersOf(winnerOf(match)).includes(player) ||
          waiting.has(player),
      )
      .map(([player]) => player),
  );
}

/** FR-049: the disabled players who stay in the draw. */
function leftPlayers(t: StoredTournament): string[] {
  const disabled = new Set(
    t.entries
      .filter((entry) => entry.stage === "main" && entry.is_disabled)
      .flatMap((entry) => entry.player_ids),
  );
  return [...playersStillIn(t)].filter((player) => disabled.has(player)).sort();
}

/** The knockout round by round (BR-155), as the organizer reads it. */
export function remixRead(t: StoredTournament): RemixRead {
  const phase = need(knockoutPhase(t));
  const rounds = remixRounds(t);
  const count = remixRoundCount(t);
  const newestNo = rounds.at(-1)?.round_no ?? 1;
  const left = new Set(leftPlayers(t));
  const fieldOf = new Map(
    t.fields.flatMap((field) =>
      field.match_id === null ? [] : [[field.match_id, field.number] as const],
    ),
  );
  const numbers = new Map<string, number>();
  let next = t.rounds
    .filter((round) => round.phase_id !== phase.id)
    .reduce((sum, round) => sum + round.matches.length, 0);
  for (const match of rounds.flatMap(inOrder)) {
    if (!isBye(match)) {
      next += 1;
      numbers.set(match.id, next);
    }
  }
  const sideView = (s: MatchSideRead): RemixSide => ({
    ...s,
    left_player_ids: s.player_ids.filter((player) => left.has(player)),
  });
  const viewOf = (round: RoundRead, match: MatchRead): RemixMatch => {
    const format = formatOf(phase, match, round.round_no === count);
    const field = fieldOf.get(match.id) ?? null;
    const bye = isBye(match);
    return {
      match_id: match.id,
      number: numbers.get(match.id) ?? null,
      position: match.position,
      kind: match.kind,
      state: bye
        ? "bye"
        : match.outcome !== null
          ? "played"
          : field !== null
            ? "on_field"
            : "ready",
      sides: [sideView(match.sides[0]), sideView(match.sides[1])],
      outcome: bye ? null : match.outcome,
      is_walkover: match.is_walkover,
      score: scoreOf(match, format),
      match_format: format,
      field_number: field,
      // BR-146: a later round is drawn, so the winner stays.
      winner_locked:
        !bye && round.round_no !== newestNo && match.outcome !== null,
    };
  };
  return {
    phase_id: phase.id,
    size: count === 0 ? 0 : 2 ** count,
    round_count: count,
    third_place_match: phase.third_place_match === true,
    match_format: phase.match_format,
    final_match_format: phase.final_match_format,
    can_draw_next: canDrawNext(t),
    left_player_ids: [...left].sort(),
    rounds: rounds.map((round): RemixRound => ({
      round_id: round.id,
      round_no: round.round_no,
      name: roundNameOf(round.round_no, count),
      result_count: round.matches.filter(
        (match) => !isBye(match) && match.outcome !== null,
      ).length,
      matches: inOrder(round).map((match) => viewOf(round, match)),
    })),
  };
}

/** FR-070: the same read for viewers, without what is the organizer's. */
export function publicRemixRead(t: StoredTournament): PublicRemixRead {
  const read = remixRead(t);
  return {
    phase_id: read.phase_id,
    size: read.size,
    round_count: read.round_count,
    third_place_match: read.third_place_match,
    match_format: read.match_format,
    final_match_format: read.final_match_format,
    left_player_ids: read.left_player_ids,
    rounds: read.rounds.map((round) => ({
      round_id: round.round_id,
      round_no: round.round_no,
      name: round.name,
      matches: round.matches.map((match) => ({
        match_id: match.match_id,
        number: match.number,
        position: match.position,
        kind: match.kind,
        state: match.state,
        sides: match.sides,
        outcome: match.outcome,
        is_walkover: match.is_walkover,
        score: match.score,
        match_format: match.match_format,
        field_number: match.field_number,
      })),
    })),
  };
}

const ROUND_NAMES: readonly RoundName[] = [
  "final",
  "semifinal",
  "quarterfinal",
  "round_of_16",
  "round_of_32",
  "round_of_64",
  "round_of_128",
  "round_of_256",
];

function roundNameOf(roundNo: number, count: number): RoundName {
  return ROUND_NAMES[count - roundNo] ?? "round_of_256";
}

/** The score from one side's view: side 2 sees the numbers the other way round. */
function scoreFor(
  match: MatchRead,
  format: RemixMatch["match_format"],
  sideNo: 1 | 2,
): [number, number] | null {
  const score = scoreOf(match, format);
  return score === null || sideNo === 1 ? score : [score[1], score[0]];
}

/**
 * BR-100 to BR-104, BR-145: one place per player. A knockout player takes the
 * place of the pair of their last match, and the pairs are placed as entries:
 * the final's winners 1st, its losers 2nd, then the third-place match, then
 * the pairs that lost the same earlier round share a place. The players who
 * did not go through follow in their group-phase order, each counting as one.
 * Before the tournament is finished there are no rows.
 */
export function remixPlaces(
  t: StoredTournament,
  table: readonly number[],
): PlacesRead {
  if (t.state !== "finished") {
    return { complete: false, rows: [] };
  }
  const phase = need(knockoutPhase(t));
  const group = groupPhase(t);
  const rounds = remixRounds(t);
  const finalRound = need(rounds.at(-1));
  const main = t.entries.filter((entry) => entry.stage === "main");
  const entryOf = new Map(
    main.flatMap((entry) =>
      entry.player_ids.map((player) => [player, entry] as const),
    ),
  );
  const groupPlace = new Map(
    rankingOf(t).rows.map((row) => [row.entry_id, row.place]),
  );
  const rankOf = (player: string): number =>
    groupPlace.get(entryOf.get(player)?.id ?? "") ?? Number.MAX_SAFE_INTEGER;

  const blocks: string[][][] = inOrder(finalRound).flatMap((match) =>
    [winnerOf(match), loserOf(match)].flatMap((team) =>
      team ? [[team.player_ids]] : [],
    ),
  );
  const earlier = rounds.slice(0, phase.third_place_match ? -2 : -1);
  for (const round of earlier.reverse()) {
    blocks.push(
      round.matches.flatMap((match) => {
        const loser = loserOf(match);
        return loser ? [loser.player_ids] : [];
      }),
    );
  }

  // The player's own last match, for the reason and the score.
  const lastMatch = new Map<string, { match: MatchRead; roundNo: number }>();
  for (const round of rounds) {
    for (const match of inOrder(round)) {
      if (!isBye(match)) {
        for (const player of match.sides.flatMap((s) => s.player_ids)) {
          lastMatch.set(player, { match, roundNo: round.round_no });
        }
      }
    }
  }
  const count = remixRoundCount(t);
  const reasonOfPlayer = (player: string, partner: string | null) => {
    const last = lastMatch.get(player);
    const entry = need(entryOf.get(player));
    const place = groupPlace.get(entry.id) ?? null;
    const base: Partial<PlaceReason> = {
      group_place: place,
      group_format: group?.format ?? null,
    };
    if (!last) {
      return reasonOf("group_place", base);
    }
    const { match, roundNo } = last;
    const sideNo = match.sides[0].player_ids.includes(player) ? 1 : 2;
    const won = playersOf(winnerOf(match)).includes(player);
    const kind: PlaceReason["kind"] =
      match.kind === "third_place"
        ? won
          ? "won_third_place"
          : "lost_third_place"
        : roundNo === count
          ? won
            ? "won_final"
            : "lost_final"
          : "lost_in_round";
    return reasonOf(kind, {
      ...base,
      round: roundNameOf(roundNo, count),
      score: scoreFor(match, formatOf(phase, match, roundNo === count), sideNo),
      partner_entry_id: partner === null ? null : need(entryOf.get(partner)).id,
    });
  };

  const decided: { place: number; entry_id: string; reason: PlaceReason }[] =
    [];
  let place = 1;
  for (const block of blocks) {
    for (const team of block) {
      const [first, second] = [...team].sort(
        (a, b) =>
          rankOf(a) - rankOf(b) ||
          (entryOf.get(a)?.seed ?? 0) - (entryOf.get(b)?.seed ?? 0),
      );
      for (const [player, partner] of [
        [need(first), need(second)],
        [need(second), need(first)],
      ] as const) {
        decided.push({
          place,
          entry_id: need(entryOf.get(player)).id,
          reason: reasonOfPlayer(player, partner),
        });
      }
    }
    place += block.length;
  }
  // BR-103: those who did not go through follow in their group-phase order.
  const inKnockout = new Set(decided.map((row) => row.entry_id));
  const rest = rankingOf(t).rows.filter((row) => !inKnockout.has(row.entry_id));
  const pairs = decided.length / 2;
  let sharedPlace = 0;
  rest.forEach((row, index) => {
    if (row.place !== sharedPlace) {
      sharedPlace = row.place;
      place = pairs + index + 1;
    }
    const player = need(
      main.find((entry) => entry.id === row.entry_id)?.player_ids[0],
    );
    decided.push({
      place,
      entry_id: row.entry_id,
      reason: reasonOfPlayer(player, null),
    });
  });

  // BR-110, BR-111: a pair (or a player who did not go through) is one unit,
  // and the units sharing a place share the points of the places they cover.
  const unitSize = (p: number) =>
    decided.find((row) => row.place === p)?.reason.kind === "group_place"
      ? 1
      : 2;
  const rowsAt = (p: number) => decided.filter((row) => row.place === p);
  return {
    complete: true,
    rows: decided.map((row): PlaceDetail => ({
      place: row.place,
      entry_id: row.entry_id,
      points_per_player: splitPlacementPoints(
        table,
        row.place,
        rowsAt(row.place).length / unitSize(row.place),
      ),
      reason: row.reason,
    })),
  };
}
