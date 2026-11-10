// demo only, the engine decides
//
// Stand-ins for the engine's setup behaviour (ADR-009, ADR-010): the league
// ranking, DYP halves and draws, seeding, the generated schedule and the
// move between setup and a started tournament. They give plausible results,
// not the backend's: the draws come from a generator seeded by the
// tournament's id and its draw counter, so a draw can be repeated.
//
// What setup stores beyond StoredTournament (the draw counter, the picked
// players, the halves, the doubles pairs) lives in a draft per tournament,
// keyed on the store's current state so that resetDemoStore() drops it too.
import type {
  DypHalfWrite,
  EntryRead,
  KnockoutMatchFormat,
  MatchFormat,
  MatchRead,
  PhaseRead,
  PreviewRound,
  RankingRow,
  RoundRead,
  SchedulePreview,
  SeedingMethod,
  TournamentFormatWrite,
  TournamentSetupRead,
} from "./contract";
import {
  createRng,
  fillFields,
  roundRobinRounds,
  waitingMatches,
} from "./engine";
import { rules } from "./rules";
import type { DemoState, StoredTournament } from "./seed";
import { activeSeason, db, seasonStandingsOf } from "./store";

/** A UUIDv7: the time in the first 48 bits, the rest random. */
export function newId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const now = Date.now();
  for (let i = 0; i < 6; i++) {
    bytes[i] = Math.floor(now / 2 ** (8 * (5 - i))) % 256;
  }
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x70;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// ---------------------------------------------------------------- draft

interface SetupDraft {
  format: TournamentFormatWrite;
  seedingMethod: SeedingMethod;
  drawCounter: number;
  playerIds: string[];
  halvesMethod: "ranking" | "by_hand";
  halves: DypHalfWrite[];
  /** Doubles: the pairs the organizer made. */
  pairs: [string, string][];
  topPlayerIds: string[];
}

const drafts = new WeakMap<DemoState, Map<string, SetupDraft>>();

function noBo2(format: MatchFormat): KnockoutMatchFormat {
  return format === "bo2" ? "bo1" : format;
}

function formatOf(t: StoredTournament): TournamentFormatWrite {
  const group = t.phases.find((phase) => phase.kind === "group");
  const knockout = t.phases.find((phase) => phase.kind === "knockout");
  const groupPhase =
    group === undefined
      ? "none"
      : group.format === "swiss" || group.format === "monster_dyp"
        ? group.format
        : "round_robin";
  return {
    name: t.name,
    date: t.date,
    type: t.type,
    group_phase: groupPhase,
    round_robin_legs: group?.round_robin_legs ?? 1,
    sit_out_points: group?.sit_out_points ?? 0,
    group_match_format: group?.match_format ?? "bo1",
    knockout_match_format: noBo2(knockout?.match_format ?? "bo1"),
    final_match_format: knockout?.final_match_format ?? null,
    third_place_match: knockout?.third_place_match ?? false,
    goals_per_game: t.goals_per_game,
    field_count: t.fields.length,
  };
}

/** The setup draft of a tournament; one is rebuilt from the data if none exists. */
function draftOf(t: StoredTournament): SetupDraft {
  const state = db();
  let map = drafts.get(state);
  if (!map) {
    map = new Map();
    drafts.set(state, map);
  }
  let draft = map.get(t.id);
  if (!draft) {
    const main = t.entries.filter((entry) => entry.stage === "main");
    draft = {
      format: formatOf(t),
      seedingMethod: "ranking",
      drawCounter: 0,
      playerIds: main.flatMap((entry) => entry.player_ids),
      halvesMethod: "ranking",
      halves:
        t.type === "dyp"
          ? main.flatMap((entry) => [
              { player_id: entry.player_ids[0] ?? "", half: "top" as const },
              { player_id: entry.player_ids[1] ?? "", half: "bottom" as const },
            ])
          : [],
      pairs:
        t.type === "doubles"
          ? main.flatMap((entry): [string, string][] =>
              entry.player_ids.length === 2
                ? [[entry.player_ids[0] ?? "", entry.player_ids[1] ?? ""]]
                : [],
            )
          : [],
      topPlayerIds: main
        .filter((entry) => entry.is_top_player)
        .flatMap((entry) => entry.player_ids),
    };
    map.set(t.id, draft);
  }
  return draft;
}

export function setupRead(t: StoredTournament): TournamentSetupRead {
  const draft = draftOf(t);
  const rank = rankOf(t.league_id);
  return {
    tournament_id: t.id,
    format: draft.format,
    seeding_method: draft.seedingMethod,
    draw_counter: draft.drawCounter,
    player_ids: byRank(draft.playerIds, rank),
    halves_method: draft.halvesMethod,
    halves: draft.halves,
    top_player_ids: draft.topPlayerIds,
  };
}

// ---------------------------------------------------------------- ranking

/** BR-020: season points, then tournament wins, then the order of the roster (the lot). */
export function leagueRanking(leagueId: string): RankingRow[] {
  const season = activeSeason(leagueId);
  const standings = new Map(
    (season ? seasonStandingsOf(season.id) : []).map((row) => [
      row.player_id,
      row,
    ]),
  );
  return db()
    .players.filter(
      (player) => player.league_id === leagueId && player.removed_at === null,
    )
    .map((player, index) => ({ player, index, row: standings.get(player.id) }))
    .sort(
      (a, b) =>
        (b.row?.points ?? 0) - (a.row?.points ?? 0) ||
        (b.row?.tournament_wins ?? 0) - (a.row?.tournament_wins ?? 0) ||
        a.index - b.index,
    )
    .map(({ player, row }, index) => ({
      rank: index + 1,
      player_id: player.id,
      points: row?.points ?? 0,
    }));
}

function rankOf(leagueId: string): Map<string, number> {
  return new Map(leagueRanking(leagueId).map((r) => [r.player_id, r.rank]));
}

function byRank(ids: readonly string[], rank: Map<string, number>): string[] {
  return [...ids].sort(
    (a, b) => (rank.get(a) ?? Infinity) - (rank.get(b) ?? Infinity),
  );
}

// ---------------------------------------------------------------- format

export interface SetupProblem {
  code: "validation_failed";
  detail: Record<string, string | number>;
}

/** The rules the format must keep; null when it keeps them. */
export function formatProblem(
  format: TournamentFormatWrite,
  drawsAllowed: boolean,
): SetupProblem | null {
  const fail = (rule: string): SetupProblem => ({
    code: "validation_failed",
    detail: { rule },
  });
  if (format.name.trim() === "") {
    return fail("name_required");
  }
  if (format.goals_per_game < 1 || format.field_count < 1) {
    return fail("positive_numbers");
  }
  // FR-031: Monster DYP plays its own rounds, the other types do not.
  if (
    (format.type === "monster_dyp") !==
    (format.group_phase === "monster_dyp")
  ) {
    return fail("FR-031");
  }
  // BR-121: BO2 is a group-phase format of leagues that allow draws.
  if (format.group_match_format === "bo2" && !drawsAllowed) {
    return fail("BR-121");
  }
  return null;
}

function buildPhases(
  current: readonly PhaseRead[],
  format: TournamentFormatWrite,
): PhaseRead[] {
  const phases: PhaseRead[] = [];
  const keep = (kind: PhaseRead["kind"]) =>
    current.find((phase) => phase.kind === kind)?.id ?? newId();
  if (format.group_phase !== "none") {
    phases.push({
      id: keep("group"),
      position: 1,
      kind: "group",
      format: format.group_phase,
      round_robin_legs:
        format.group_phase === "round_robin" ? format.round_robin_legs : null,
      sit_out_points: format.sit_out_points,
      tiebreakers:
        format.group_phase === "round_robin"
          ? null
          : [...rules.swissTiebreakers],
      qualifiers: null,
      third_place_match: null,
      monster_knockout_mode: null,
      match_format: format.group_match_format,
      final_match_format: null,
    });
  } else {
    phases.push({
      id: keep("knockout"),
      position: 1,
      kind: "knockout",
      format: "single_elimination",
      round_robin_legs: null,
      sit_out_points: null,
      tiebreakers: null,
      qualifiers: null,
      third_place_match: format.third_place_match,
      monster_knockout_mode: null,
      match_format: format.knockout_match_format,
      final_match_format: format.final_match_format,
    });
  }
  return phases;
}

export function createTournament(
  id: string,
  leagueId: string,
  seasonId: string,
  format: TournamentFormatWrite,
): StoredTournament {
  const t: StoredTournament = {
    id,
    league_id: leagueId,
    season_id: seasonId,
    name: format.name,
    date: format.date,
    type: format.type,
    state: "setup",
    goals_per_game: format.goals_per_game,
    phases: buildPhases([], format),
    entries: [],
    rounds: [],
    fields: [],
  };
  syncFields(t, format.field_count);
  db().tournaments.push(t);
  const map = drafts.get(db()) ?? new Map<string, SetupDraft>();
  drafts.set(db(), map);
  map.set(id, {
    format,
    seedingMethod: "ranking",
    drawCounter: 0,
    playerIds: [],
    halvesMethod: "ranking",
    halves: [],
    pairs: [],
    topPlayerIds: [],
  });
  return t;
}

function syncFields(t: StoredTournament, count: number): void {
  t.fields = Array.from(
    { length: count },
    (_, index) =>
      t.fields[index] ?? { id: newId(), number: index + 1, match_id: null },
  );
}

export function applyFormat(
  t: StoredTournament,
  format: TournamentFormatWrite,
): void {
  const draft = draftOf(t);
  const typeChanged = t.type !== format.type;
  draft.format = format;
  t.name = format.name;
  t.date = format.date;
  t.type = format.type;
  t.goals_per_game = format.goals_per_game;
  t.phases = buildPhases(t.phases, format);
  syncFields(t, format.field_count);
  if (typeChanged) {
    draft.pairs = [];
    draft.halves = [];
    draft.halvesMethod = "ranking";
    draft.topPlayerIds = [];
    rebuildEntries(t, draft, "draw");
  }
}

// ---------------------------------------------------------------- draws

/** A generator for one draw: the tournament's id and the draw counter fix it. */
function rngFor(t: StoredTournament, drawCounter: number): () => number {
  let hash = 2166136261;
  for (const char of t.id) {
    hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  }
  return createRng(hash + drawCounter * 7919);
}

function shuffled<T>(items: readonly T[], rng: () => number): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [result[i], result[j]] = [result[j] as T, result[i] as T];
  }
  return result;
}

function halfOf(
  draft: SetupDraft,
  playerId: string,
): DypHalfWrite["half"] | undefined {
  return draft.halves.find((row) => row.player_id === playerId)?.half;
}

/** BR-032: the halves by the league ranking; an odd one out is drawn by lot. */
function halvesByRanking(
  ranked: readonly string[],
  rng: () => number,
): DypHalfWrite[] {
  let pool = [...ranked];
  const rows: DypHalfWrite[] = [];
  if (pool.length % 2 === 1) {
    const index = Math.floor(rng() * pool.length);
    rows.push({ player_id: pool[index] ?? "", half: "left_out" });
    pool = pool.filter((_, i) => i !== index);
  }
  const half = pool.length / 2;
  return [
    ...pool
      .slice(0, half)
      .map((id) => ({ player_id: id, half: "top" as const })),
    ...pool
      .slice(half)
      .map((id) => ({ player_id: id, half: "bottom" as const })),
    ...rows,
  ];
}

type Grouping = "draw" | "keep";

/**
 * Rebuilds the entries from the draft. "draw" makes new pairs (DYP) or new
 * entries and counts a draw; "keep" only seeds the entries again.
 */
function rebuildEntries(
  t: StoredTournament,
  draft: SetupDraft,
  grouping: Grouping,
): void {
  const rank = rankOf(t.league_id);
  const ranked = byRank(draft.playerIds, rank);
  let groups: string[][];
  if (grouping === "draw") {
    draft.drawCounter += 1;
    const rng = rngFor(t, draft.drawCounter);
    switch (t.type) {
      case "singles":
      case "monster_dyp":
        groups = ranked.map((id) => [id]);
        break;
      case "doubles":
        groups = draft.pairs.map((pair) => [...pair]);
        break;
      case "dyp": {
        if (draft.halvesMethod === "ranking") {
          draft.halves = halvesByRanking(ranked, rng);
        }
        const top = ranked.filter((id) => halfOf(draft, id) === "top");
        const bottom = ranked.filter((id) => halfOf(draft, id) === "bottom");
        const complete = ranked.every((id) => halfOf(draft, id) !== undefined);
        // BR-033: each top-half player gets a partner by lot.
        const partners = shuffled(bottom, rng);
        groups =
          complete && top.length === bottom.length
            ? top.map((id, i) => [id, partners[i] ?? ""])
            : [];
        break;
      }
    }
  } else {
    groups = t.entries
      .filter((entry) => entry.stage === "main")
      .map((entry) => [...entry.player_ids]);
  }
  seed(t, draft, groups, rank);
}

function seed(
  t: StoredTournament,
  draft: SetupDraft,
  groups: string[][],
  rank: Map<string, number>,
): void {
  const previous = new Map(
    t.entries.map((entry) => [[...entry.player_ids].sort().join("+"), entry]),
  );
  const rankOfMember = (id: string) => rank.get(id) ?? Infinity;
  let ordered = groups;
  if (t.type !== "monster_dyp") {
    if (draft.seedingMethod === "random") {
      ordered = shuffled(groups, createRng(draft.drawCounter * 104729 + 1));
    } else {
      // BR-021: pairs by the sum of their ranking positions, then the better player.
      ordered = [...groups].sort(
        (a, b) =>
          a.reduce((sum, id) => sum + rankOfMember(id), 0) -
            b.reduce((sum, id) => sum + rankOfMember(id), 0) ||
          Math.min(...a.map(rankOfMember)) - Math.min(...b.map(rankOfMember)),
      );
    }
  }
  t.entries = ordered.map((members, index): EntryRead => {
    const old = previous.get([...members].sort().join("+"));
    return {
      id: old?.id ?? newId(),
      stage: "main",
      kind: members.length === 1 ? "player" : "pair",
      seed: t.type === "monster_dyp" ? null : index + 1,
      player_ids: members,
      is_disabled: false,
      is_top_player: members.every((id) => draft.topPlayerIds.includes(id)),
    };
  });
}

// ---------------------------------------------------------------- setup writes

export type SetupFailure =
  | {
      status: 409;
      code:
        | "draw_counter_changed"
        | "seed_order_changed"
        | "tournament_not_in_setup";
    }
  | {
      status: 422;
      code: "validation_failed";
      detail: Record<string, string | number>;
    };

const invalid = (
  rule: string,
  extra: Record<string, string | number> = {},
): SetupFailure => ({
  status: 422,
  code: "validation_failed",
  detail: { rule, ...extra },
});

function leaguePlayerIds(t: StoredTournament): Set<string> {
  return new Set(
    db()
      .players.filter(
        (p) => p.league_id === t.league_id && p.removed_at === null,
      )
      .map((p) => p.id),
  );
}

export function setPlayers(
  t: StoredTournament,
  playerIds: readonly string[],
): SetupFailure | null {
  const draft = draftOf(t);
  const known = leaguePlayerIds(t);
  const unique = [...new Set(playerIds)];
  // BR-002: a removed player cannot be picked.
  if (!unique.every((id) => known.has(id))) {
    return invalid("BR-002");
  }
  const same =
    unique.length === draft.playerIds.length &&
    unique.every((id) => draft.playerIds.includes(id));
  if (same) {
    return null;
  }
  draft.playerIds = unique;
  draft.pairs = draft.pairs.filter(
    ([a, b]) => unique.includes(a) && unique.includes(b),
  );
  draft.halves = draft.halves.filter((row) => unique.includes(row.player_id));
  draft.topPlayerIds = draft.topPlayerIds.filter((id) => unique.includes(id));
  rebuildEntries(t, draft, "draw");
  return null;
}

export function setHalves(
  t: StoredTournament,
  method: "ranking" | "by_hand",
  halves: readonly DypHalfWrite[],
): SetupFailure | null {
  const draft = draftOf(t);
  if (t.type !== "dyp") {
    return invalid("BR-032");
  }
  draft.halvesMethod = method;
  if (method === "by_hand") {
    draft.halves = halves.filter((row) =>
      draft.playerIds.includes(row.player_id),
    );
  }
  rebuildEntries(t, draft, "draw");
  return null;
}

export function setPairs(
  t: StoredTournament,
  pairs: readonly [string, string][],
): SetupFailure | null {
  const draft = draftOf(t);
  const members = pairs.flat();
  // BR-003, BR-030: two different, picked players, each in one pair.
  if (
    t.type !== "doubles" ||
    new Set(members).size !== members.length ||
    !members.every((id) => draft.playerIds.includes(id))
  ) {
    return invalid("BR-003");
  }
  draft.pairs = pairs.map(([a, b]) => [a, b]);
  rebuildEntries(t, draft, "draw");
  return null;
}

export function setTopPlayers(
  t: StoredTournament,
  playerIds: readonly string[],
): SetupFailure | null {
  const draft = draftOf(t);
  if (
    t.type !== "monster_dyp" ||
    !playerIds.every((id) => draft.playerIds.includes(id))
  ) {
    return invalid("FR-041");
  }
  draft.topPlayerIds = [...playerIds];
  for (const entry of t.entries) {
    entry.is_top_player = entry.player_ids.every((id) =>
      playerIds.includes(id),
    );
  }
  return null;
}

export function setSeeding(
  t: StoredTournament,
  method: SeedingMethod,
): SetupFailure | null {
  const draft = draftOf(t);
  if (t.type === "monster_dyp") {
    return invalid("FR-034");
  }
  draft.seedingMethod = method;
  if (method === "random") {
    draft.drawCounter += 1;
  }
  rebuildEntries(t, draft, "keep");
  return null;
}

export function setSeedOrder(
  t: StoredTournament,
  entryIds: readonly string[],
): SetupFailure | null {
  const current = t.entries.filter((entry) => entry.stage === "main");
  // ADR-008: an order that does not list exactly the current entries is stale.
  if (
    entryIds.length !== current.length ||
    !current.every((entry) => entryIds.includes(entry.id))
  ) {
    return { status: 409, code: "seed_order_changed" };
  }
  t.entries = entryIds.flatMap((id, index) => {
    const entry = current.find((e) => e.id === id);
    return entry ? [{ ...entry, seed: index + 1 }] : [];
  });
  return null;
}

export function drawAgain(
  t: StoredTournament,
  target: "pairs" | "seeds",
  expectedCounter: number,
): SetupFailure | null {
  const draft = draftOf(t);
  if (draft.drawCounter !== expectedCounter) {
    return { status: 409, code: "draw_counter_changed" };
  }
  if (target === "seeds") {
    draft.drawCounter += 1;
    rebuildEntries(t, draft, "keep");
    return null;
  }
  if (t.type === "doubles") {
    // The players without a partner are paired at random.
    const paired = new Set(draft.pairs.flat());
    const rest = shuffled(
      byRank(draft.playerIds, rankOf(t.league_id)).filter(
        (id) => !paired.has(id),
      ),
      rngFor(t, draft.drawCounter + 1),
    );
    for (let i = 0; i + 1 < rest.length; i += 2) {
      draft.pairs.push([rest[i] ?? "", rest[i + 1] ?? ""]);
    }
    rebuildEntries(t, draft, "draw");
    return null;
  }
  rebuildEntries(t, draft, "draw");
  return null;
}

// ---------------------------------------------------------------- schedule

interface Side {
  entry: EntryRead | null;
  players: string[];
}

function sideOf(entry: EntryRead): Side {
  return { entry, players: entry.player_ids };
}

function powerOfTwoAtLeast(n: number): number {
  let size = 2;
  while (size < n) {
    size *= 2;
  }
  return size;
}

/** The seeds in bracket order, so that seeds 1 and 2 meet only in the final (BR-042). */
function bracketOrder(size: number): number[] {
  let order = [1];
  while (order.length < size) {
    const total = order.length * 2 + 1;
    order = order.flatMap((seedNo) => [seedNo, total - seedNo]);
  }
  return order;
}

interface Plan {
  rounds: { sides: [Side, Side][]; sittingOut: Side[] }[];
  matchCount: number | null;
  roundCount: number | null;
  bracketSize: number | null;
}

function plan(t: StoredTournament, draft: SetupDraft): Plan {
  const rank = rankOf(t.league_id);
  const entries = t.entries.filter((entry) => entry.stage === "main");
  const sorted = [...entries].sort(
    (a, b) => (a.seed ?? Infinity) - (b.seed ?? Infinity),
  );
  switch (draft.format.group_phase) {
    case "round_robin": {
      const once = roundRobinRounds(sorted);
      const all =
        draft.format.round_robin_legs === 2
          ? [
              ...once,
              ...once.map((pairing) => ({
                matches: pairing.matches.map(([a, b]): [typeof a, typeof b] => [
                  b,
                  a,
                ]),
                sittingOut: pairing.sittingOut,
              })),
            ]
          : once;
      const rounds = all.map((pairing) => ({
        sides: pairing.matches.map(([a, b]): [Side, Side] => [
          sideOf(a),
          sideOf(b),
        ]),
        sittingOut: pairing.sittingOut.map(sideOf),
      }));
      return {
        rounds,
        matchCount: rounds.reduce((sum, round) => sum + round.sides.length, 0),
        roundCount: rounds.length,
        bracketSize: null,
      };
    }
    case "swiss": {
      // Round 1: the top half against the bottom half, by seed.
      const half = Math.floor(sorted.length / 2);
      const sides = sorted
        .slice(0, half)
        .map((entry, i): [Side, Side] => [
          sideOf(entry),
          sideOf(sorted[i + half] ?? entry),
        ]);
      const sittingOut =
        sorted.length % 2 === 1 ? sorted.slice(-1).map(sideOf) : [];
      return {
        rounds: [{ sides, sittingOut }],
        matchCount: null,
        roundCount: null,
        bracketSize: null,
      };
    }
    case "monster_dyp": {
      // Round 1: groups of four, one top player in each, two teams of two.
      const ranked = byRank(
        sorted.flatMap((e) => e.player_ids),
        rank,
      );
      const groupsOfFour = Math.floor(ranked.length / 4);
      const marked = draft.topPlayerIds.filter((id) => ranked.includes(id));
      const top = [
        ...marked,
        ...ranked.filter((id) => !marked.includes(id)),
      ].slice(0, groupsOfFour);
      const rest = shuffled(
        ranked.filter((id) => !top.includes(id)),
        rngFor(t, draft.drawCounter),
      );
      const byPlayer = new Map(sorted.map((e) => [e.player_ids[0] ?? "", e]));
      const side = (...ids: string[]): Side => ({
        entry: null,
        players: ids,
      });
      const sides = top.map((id, i): [Side, Side] => [
        side(id, rest[i * 3] ?? ""),
        side(rest[i * 3 + 1] ?? "", rest[i * 3 + 2] ?? ""),
      ]);
      const sittingOut = rest
        .slice(groupsOfFour * 3)
        .flatMap((id) => byPlayer.get(id) ?? [])
        .map((entry): Side => ({ entry, players: entry.player_ids }));
      return {
        rounds: [{ sides, sittingOut }],
        matchCount: null,
        roundCount: null,
        bracketSize: null,
      };
    }
    case "none": {
      // BR-040–BR-042: byes go to the top seeds; later rounds wait for winners.
      const size = powerOfTwoAtLeast(sorted.length);
      const slots = bracketOrder(size).map((seedNo) => sorted[seedNo - 1]);
      const first: [Side, Side][] = [];
      for (let i = 0; i < slots.length; i += 2) {
        const a = slots[i];
        const b = slots[i + 1];
        if (a && b) {
          first.push([sideOf(a), sideOf(b)]);
        }
      }
      const rounds = [{ sides: first, sittingOut: [] as Side[] }];
      for (let n = size / 4; n >= 1; n /= 2) {
        rounds.push({
          sides: Array.from({ length: n }, (): [Side, Side] => [
            { entry: null, players: [] },
            { entry: null, players: [] },
          ]),
          sittingOut: [],
        });
      }
      return {
        rounds,
        matchCount:
          sorted.length - 1 + (draft.format.third_place_match ? 1 : 0),
        roundCount: rounds.length,
        bracketSize: size,
      };
    }
  }
}

export function preview(t: StoredTournament): SchedulePreview {
  const draft = draftOf(t);
  const made = plan(t, draft);
  const shown: PreviewRound[] =
    made.bracketSize === null
      ? made.rounds.map((round, index) => ({
          round_no: index + 1,
          matches: round.sides.map(([a, b]) => ({
            sides: [a.players, b.players],
          })),
          sitting_out: round.sittingOut.map((side) => side.players),
        }))
      : made.rounds.slice(0, 1).map((round, index) => ({
          round_no: index + 1,
          matches: round.sides.map(([a, b]) => ({
            sides: [a.players, b.players],
          })),
          sitting_out: [],
        }));
  return {
    rounds: shown,
    match_count: made.matchCount,
    round_count: made.roundCount,
    bracket_size: made.bracketSize,
  };
}

/** The reason the tournament cannot start (FR-032, BR-031); null when it can. */
export function startProblem(t: StoredTournament): SetupFailure | null {
  const draft = draftOf(t);
  const entries = t.entries.filter((entry) => entry.stage === "main");
  const minimum =
    t.type === "monster_dyp"
      ? 4
      : draft.format.group_phase === "none" && draft.format.third_place_match
        ? 4
        : 2;
  const count =
    t.type === "monster_dyp" ? draft.playerIds.length : entries.length;
  return count < minimum
    ? invalid("FR-032", { min: minimum, given: count })
    : null;
}

export function start(
  t: StoredTournament,
  expectedCounter: number,
): SetupFailure | null {
  const draft = draftOf(t);
  if (t.state !== "setup") {
    return { status: 409, code: "tournament_not_in_setup" };
  }
  if (draft.drawCounter !== expectedCounter) {
    return { status: 409, code: "draw_counter_changed" };
  }
  const problem = startProblem(t);
  if (problem) {
    return problem;
  }
  const phase = t.phases[0];
  if (!phase) {
    return invalid("FR-035");
  }
  const made = plan(t, draft);
  t.rounds = made.rounds.map((round, index): RoundRead => {
    const roundId = newId();
    return {
      id: roundId,
      phase_id: phase.id,
      round_no: index + 1,
      matches: round.sides.map(([a, b], position): MatchRead => ({
        id: newId(),
        round_id: roundId,
        position: position + 1,
        kind: "standard",
        sides: [
          {
            entry_id: a.entry?.id ?? null,
            player_ids: a.players,
            is_bye: false,
          },
          {
            entry_id: b.entry?.id ?? null,
            player_ids: b.players,
            is_bye: false,
          },
        ],
        outcome: null,
        is_walkover: false,
        games: [],
        result_entered_at: null,
      })),
      sitting_out: round.sittingOut.flatMap((side) => side.entry?.id ?? []),
    };
  });
  const matchesById = new Map(
    t.rounds
      .flatMap((round) => round.matches)
      .map((match) => [match.id, match]),
  );
  t.fields = fillFields(
    t.fields,
    waitingMatches(t.rounds, t.fields),
    matchesById,
  );
  t.state = "in_progress";
  return null;
}

/** FR-036: back to setup is possible until the first result is entered. */
export function backToSetup(
  t: StoredTournament,
  expectedState: string,
): SetupFailure | null {
  if (t.state !== expectedState) {
    return { status: 409, code: "tournament_not_in_setup" };
  }
  if (t.state !== "in_progress") {
    return invalid("FR-036");
  }
  if (t.rounds.some((round) => round.matches.some((m) => m.outcome !== null))) {
    return invalid("FR-036");
  }
  draftOf(t);
  t.rounds = [];
  t.fields = t.fields.map((field) => ({ ...field, match_id: null }));
  for (const entry of t.entries) {
    // DATA-MODEL §4.4: going back to setup clears "disabled".
    entry.is_disabled = false;
  }
  t.state = "setup";
  return null;
}

export function deleteTournament(t: StoredTournament): SetupFailure | null {
  const season = db().seasons.find((s) => s.id === t.season_id);
  // FR-038: not in a closed season.
  if (season?.state === "closed") {
    return invalid("FR-038");
  }
  const state = db();
  state.tournaments = state.tournaments.filter((other) => other.id !== t.id);
  return null;
}
