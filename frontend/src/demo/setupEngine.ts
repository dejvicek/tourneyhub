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
import type { components } from "@/api/schema";
import { defaultSitOutPoints } from "@/lib/sitOutPoints";

import type { EntryRead, MatchRead, PhaseRead, RoundRead } from "./contract";
import {
  createRng,
  fillFields,
  roundRobinRounds,
  waitingMatches,
} from "./engine";
import { rules } from "./rules";
import type { DemoState, StoredLeague, StoredTournament } from "./seed";
import { activeSeason, db, seasonStandingsOf } from "./store";

type Schemas = components["schemas"];
type FormatRead = Schemas["TournamentFormatRead"];
type FormatWrite = Schemas["TournamentFormatWrite"];
type TournamentCreate = Schemas["TournamentCreate"];
type DypHalfRead = Schemas["DypHalfRead"];
type RankingRow = Schemas["RankingRow"];
type SeedingMethod = Schemas["SeedingMethod"];
type ErrorCode = Schemas["ErrorCode"];
type SchedulePreview = Schemas["SchedulePreviewRead"];
type PreviewRound = Schemas["PreviewRoundRead"];

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
  format: FormatRead;
  seedingMethod: SeedingMethod;
  drawCounter: number;
  playerIds: string[];
  halvesMethod: "ranking" | "by_hand";
  halves: DypHalfRead[];
  /** Doubles: the pairs the organizer made. */
  pairs: [string, string][];
  topPlayerIds: string[];
}

const drafts = new WeakMap<DemoState, Map<string, SetupDraft>>();

/** The stored format; the settings the phases do not use are null (FR-031). */
function formatOf(t: StoredTournament): FormatRead {
  const group = t.phases.find((phase) => phase.kind === "group");
  const knockout = group
    ? undefined
    : t.phases.find((phase) => phase.kind === "knockout");
  return {
    name: t.name,
    date: t.date,
    type: t.type,
    group_phase:
      group === undefined
        ? "none"
        : group.format === "single_elimination"
          ? "round_robin"
          : group.format,
    round_robin_legs: group?.round_robin_legs ?? null,
    sit_out_points: group?.sit_out_points ?? null,
    sit_out_points_set_by_hand: group?.sit_out_points_set_by_hand ?? null,
    group_match_format: group?.match_format ?? null,
    knockout_match_format:
      knockout === undefined || knockout.match_format === "bo2"
        ? null
        : knockout.match_format,
    final_match_format: knockout?.final_match_format ?? null,
    third_place_match: knockout?.third_place_match ?? null,
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

/** How many players are picked for a tournament in setup (screen 1). */
export function pickedCount(t: StoredTournament): number {
  return draftOf(t).playerIds.length;
}

/** BR-002: whether the player is picked for the tournament (setup) or plays in it. */
export function isPicked(t: StoredTournament, playerId: string): boolean {
  return draftOf(t).playerIds.includes(playerId);
}

export function setupRead(t: StoredTournament): Schemas["TournamentSetupRead"] {
  const draft = draftOf(t);
  const ranking = leagueRanking(t.league_id);
  const rank = new Map(ranking.map((r) => [r.player_id, r.rank]));
  return {
    tournament_id: t.id,
    state: t.state,
    format: draft.format,
    seeding_method: draft.seedingMethod,
    draw_counter: draft.drawCounter,
    player_ids: byRank(draft.playerIds, rank),
    halves_method: draft.halvesMethod,
    halves: draft.halves,
    top_player_ids: draft.topPlayerIds,
    entries: t.entries
      .filter((entry) => entry.stage === "main")
      .toSorted((a, b) => (a.seed ?? 0) - (b.seed ?? 0))
      .map(
        ({
          id,
          stage,
          kind,
          seed,
          player_ids,
          is_disabled,
          is_top_player,
        }) => ({
          id,
          stage,
          kind,
          seed,
          player_ids,
          is_disabled,
          is_top_player,
        }),
      ),
    ranking,
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

/** A refusal in the API's shape, as the backend's services make them (ADR-008). */
export interface SetupFailure {
  status: 404 | 409 | 422;
  code: ErrorCode;
  detail: Schemas["ErrorResponse"]["detail"];
}

const fail = (
  status: SetupFailure["status"],
  code: ErrorCode,
  detail: SetupFailure["detail"] = {},
): SetupFailure => ({ status, code, detail });

/** A request body the backend's validation refuses (422 `validation_failed`). */
const invalidBody = (type: string): SetupFailure =>
  fail(422, "validation_failed", { errors: [{ loc: ["body"], type }] });

const GROUP_SETTINGS = [
  "round_robin_legs",
  "sit_out_points",
  "group_match_format",
] as const;
const KNOCKOUT_SETTINGS = [
  "knockout_match_format",
  "final_match_format",
  "third_place_match",
] as const;

/**
 * FR-031 as the backend checks it: Monster DYP plays its own rounds, and the
 * settings of the phases that are not played are null. With `complete` (the
 * format PUT), every setting that applies is given.
 */
function formatProblem(
  format: FormatWrite | TournamentCreate,
  drawsAllowed: boolean,
  complete: boolean,
): SetupFailure | null {
  if (
    (format.type === "monster_dyp") !==
    (format.group_phase === "monster_dyp")
  ) {
    return invalidBody("group_phase_mismatch");
  }
  if (format.name.trim() === "") {
    return invalidBody("string_too_short");
  }
  const grouped = format.group_phase !== "none";
  const applies = new Set<string>(grouped ? GROUP_SETTINGS : KNOCKOUT_SETTINGS);
  if (format.group_phase !== "round_robin") {
    applies.delete("round_robin_legs");
  }
  for (const name of [...GROUP_SETTINGS, ...KNOCKOUT_SETTINGS]) {
    const value = format[name] ?? null;
    if (!applies.has(name) && value !== null) {
      return invalidBody("setting_not_applicable");
    }
    if (
      complete &&
      applies.has(name) &&
      name !== "final_match_format" &&
      name !== "sit_out_points" &&
      value === null
    ) {
      return invalidBody("setting_missing");
    }
  }
  // BR-121: BO2 is a group-phase format of leagues that allow draws.
  if (format.group_match_format === "bo2" && !drawsAllowed) {
    return fail(422, "draws_not_allowed");
  }
  return null;
}

/** What the request left out, from the league's defaults (FR-011, FR-030). */
function resolveFormat(
  format: FormatWrite | TournamentCreate,
  league: StoredLeague,
): FormatRead {
  const grouped = format.group_phase !== "none";
  const fallback = league.default_match_format;
  const groupMatchFormat = format.group_match_format ?? fallback;
  // BR-071: a number is the organizer's pick; null takes the match format's default.
  const picked = format.sit_out_points ?? null;
  return {
    name: format.name.trim(),
    date: format.date,
    type: format.type,
    group_phase: format.group_phase,
    round_robin_legs:
      format.group_phase === "round_robin"
        ? (format.round_robin_legs ?? 1)
        : null,
    sit_out_points: grouped
      ? (picked ?? defaultSitOutPoints(groupMatchFormat))
      : null,
    sit_out_points_set_by_hand: grouped ? picked !== null : null,
    group_match_format: grouped ? groupMatchFormat : null,
    knockout_match_format: grouped
      ? null
      : (format.knockout_match_format ?? fallback),
    final_match_format: grouped ? null : (format.final_match_format ?? null),
    third_place_match: grouped ? null : (format.third_place_match ?? false),
    goals_per_game: format.goals_per_game ?? league.default_goals_per_game,
    field_count: format.field_count ?? league.default_field_count,
  };
}

function buildPhases(
  current: readonly PhaseRead[],
  format: FormatRead,
): PhaseRead[] {
  const keep = (kind: PhaseRead["kind"]) =>
    current.find((phase) => phase.kind === kind)?.id ?? newId();
  if (format.group_phase !== "none") {
    return [
      {
        id: keep("group"),
        position: 1,
        kind: "group",
        format: format.group_phase,
        round_robin_legs: format.round_robin_legs,
        sit_out_points: format.sit_out_points,
        sit_out_points_set_by_hand: format.sit_out_points_set_by_hand ?? false,
        tiebreakers:
          format.group_phase === "round_robin"
            ? null
            : [...rules.swissTiebreakers],
        qualifiers: null,
        third_place_match: null,
        monster_knockout_mode: null,
        match_format: format.group_match_format ?? "bo1",
        final_match_format: null,
      },
    ];
  }
  return [
    {
      id: keep("knockout"),
      position: 1,
      kind: "knockout",
      format: "single_elimination",
      round_robin_legs: null,
      sit_out_points: null,
      sit_out_points_set_by_hand: false,
      tiebreakers: null,
      qualifiers: null,
      third_place_match: format.third_place_match ?? false,
      monster_knockout_mode: null,
      match_format: format.knockout_match_format ?? "bo1",
      final_match_format: format.final_match_format,
    },
  ];
}

/** POST …/tournaments: the checks, then a new tournament in the active season. */
export function createTournament(
  body: TournamentCreate,
  league: StoredLeague,
  seasonId: string,
): StoredTournament | SetupFailure {
  const problem = formatProblem(body, league.draws_allowed, false);
  if (problem) {
    return problem;
  }
  const format = resolveFormat(body, league);
  const t: StoredTournament = {
    id: body.id,
    league_id: league.id,
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
  map.set(t.id, {
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

/** PUT …/format: the whole format as the target state (FR-030). */
export function applyFormat(
  t: StoredTournament,
  body: FormatWrite,
  league: StoredLeague,
): SetupFailure | null {
  const problem = formatProblem(body, league.draws_allowed, true);
  if (problem) {
    return problem;
  }
  const format = resolveFormat(body, league);
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
  return null;
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
): DypHalfRead["half"] | undefined {
  return draft.halves.find((row) => row.player_id === playerId)?.half;
}

/** BR-032: the halves by the league ranking; an odd one out is drawn by lot. */
function halvesByRanking(
  ranked: readonly string[],
  rng: () => number,
): DypHalfRead[] {
  // BR-031: fewer than four players have no halves yet.
  if (ranked.length < 4) {
    return [];
  }
  let pool = [...ranked];
  const rows: DypHalfRead[] = [];
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
        const leftOut = ranked.filter((id) => halfOf(draft, id) === "left_out");
        const complete =
          ranked.length >= 4 &&
          leftOut.length <= 1 &&
          ranked.every((id) => halfOf(draft, id) !== undefined);
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
// The backend's rules and codes (backend/src/tourneyhub/services/tournaments.py).

const typeChanged = (t: StoredTournament): SetupFailure =>
  fail(409, "tournament_type_changed", { type: t.type });

/** 409 when a player is not picked: the screen that sent it is stale. */
function notPicked(
  draft: SetupDraft,
  playerIds: readonly string[],
): SetupFailure | null {
  const missing = playerIds.find((id) => !draft.playerIds.includes(id));
  return missing === undefined
    ? null
    : fail(409, "player_not_picked", { player_id: missing });
}

export function setPlayers(
  t: StoredTournament,
  playerIds: readonly string[],
): SetupFailure | null {
  const draft = draftOf(t);
  if (new Set(playerIds).size !== playerIds.length) {
    return invalidBody("given_twice");
  }
  const league = db().players.filter((p) => p.league_id === t.league_id);
  const unknown = playerIds.find((id) => !league.some((p) => p.id === id));
  if (unknown !== undefined) {
    return fail(404, "player_not_found");
  }
  // BR-002: a removed player cannot be picked; only a screen that was not
  // reloaded after the removal offers one, so it is a 409 (ADR-008).
  const removed = playerIds.find(
    (id) => league.find((p) => p.id === id)?.removed_at !== null,
  );
  if (removed !== undefined) {
    return fail(409, "player_removed", { player_id: removed });
  }
  const same =
    playerIds.length === draft.playerIds.length &&
    playerIds.every((id) => draft.playerIds.includes(id));
  if (same) {
    return null;
  }
  draft.playerIds = [...playerIds];
  draft.pairs = draft.pairs.filter(
    ([a, b]) => playerIds.includes(a) && playerIds.includes(b),
  );
  draft.halves = draft.halves.filter((row) =>
    playerIds.includes(row.player_id),
  );
  draft.topPlayerIds = draft.topPlayerIds.filter((id) =>
    playerIds.includes(id),
  );
  rebuildEntries(t, draft, "draw");
  return null;
}

export function setHalves(
  t: StoredTournament,
  method: "ranking" | "by_hand",
  halves: readonly DypHalfRead[],
): SetupFailure | null {
  const draft = draftOf(t);
  if (t.type !== "dyp") {
    return typeChanged(t);
  }
  if (new Set(halves.map((row) => row.player_id)).size !== halves.length) {
    return invalidBody("given_twice");
  }
  if (method === "by_hand") {
    const stale = notPicked(
      draft,
      halves.map((row) => row.player_id),
    );
    if (stale) {
      return stale;
    }
    const same =
      draft.halvesMethod === "by_hand" &&
      halves.length === draft.halves.length &&
      halves.every((row) => halfOf(draft, row.player_id) === row.half);
    if (same) {
      return null;
    }
    draft.halves = halves.map(({ player_id, half }) => ({ player_id, half }));
  } else if (draft.halvesMethod === method) {
    return null;
  }
  draft.halvesMethod = method;
  rebuildEntries(t, draft, "draw");
  return null;
}

export function setPairs(
  t: StoredTournament,
  pairs: readonly [string, string][],
): SetupFailure | null {
  const draft = draftOf(t);
  if (t.type !== "doubles") {
    return typeChanged(t);
  }
  const members = pairs.flat();
  // BR-003, BR-030: two different players, each in one pair.
  if (new Set(members).size !== members.length) {
    return invalidBody("given_twice");
  }
  const stale = notPicked(draft, members);
  if (stale) {
    return stale;
  }
  const key = (pair: readonly string[]) => [...pair].sort().join("+");
  const wanted = new Set(pairs.map(key));
  if (
    wanted.size === draft.pairs.length &&
    draft.pairs.every((pair) => wanted.has(key(pair)))
  ) {
    return null;
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
  if (t.type !== "monster_dyp") {
    return typeChanged(t);
  }
  const stale = notPicked(draft, playerIds);
  if (stale) {
    return stale;
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
    return typeChanged(t);
  }
  if (draft.seedingMethod === method) {
    return null;
  }
  draft.seedingMethod = method;
  draft.drawCounter += 1;
  rebuildEntries(t, draft, "keep");
  return null;
}

export function setSeedOrder(
  t: StoredTournament,
  entryIds: readonly string[],
): SetupFailure | null {
  if (t.type === "monster_dyp") {
    return typeChanged(t);
  }
  if (new Set(entryIds).size !== entryIds.length) {
    return invalidBody("given_twice");
  }
  const current = t.entries.filter((entry) => entry.stage === "main");
  // ADR-008: an order that does not list exactly the current entries is stale.
  if (
    entryIds.length !== current.length ||
    !current.every((entry) => entryIds.includes(entry.id))
  ) {
    return fail(409, "seed_order_changed");
  }
  t.entries = entryIds.flatMap((id, index) => {
    const entry = current.find((e) => e.id === id);
    return entry ? [{ ...entry, seed: index + 1 }] : [];
  });
  return null;
}

/** Why a new DYP draw cannot make pairs (BR-031, BR-032); null when it can. */
function dypDrawProblem(draft: SetupDraft): SetupFailure | null {
  const players = draft.playerIds.length;
  if (draft.halvesMethod === "ranking") {
    return players < 4
      ? fail(422, "not_enough_players", { minimum: 4, given: players })
      : null;
  }
  const missing = draft.playerIds.filter(
    (id) => halfOf(draft, id) === undefined,
  ).length;
  if (missing > 0) {
    return fail(422, "dyp_halves_incomplete", { missing });
  }
  if (players < 4) {
    return fail(422, "not_enough_players", { minimum: 4, given: players });
  }
  const count = (half: DypHalfRead["half"]) =>
    draft.halves.filter((row) => row.half === half).length;
  if (count("left_out") > 1) {
    return fail(422, "too_many_left_out", {
      maximum: 1,
      given: count("left_out"),
    });
  }
  if (count("top") !== count("bottom")) {
    return fail(422, "dyp_halves_unequal", {
      top: count("top"),
      bottom: count("bottom"),
    });
  }
  return null;
}

export function drawAgain(
  t: StoredTournament,
  target: "pairs" | "seeds",
  expectedCounter: number,
): SetupFailure | null {
  const draft = draftOf(t);
  if (draft.drawCounter !== expectedCounter) {
    return fail(409, "draw_counter_changed", {
      draw_counter: draft.drawCounter,
    });
  }
  if (target === "seeds") {
    if (t.type === "monster_dyp") {
      return typeChanged(t);
    }
    if (draft.seedingMethod !== "random") {
      return fail(409, "seeding_method_changed", {
        seeding_method: draft.seedingMethod,
      });
    }
    draft.drawCounter += 1;
    rebuildEntries(t, draft, "keep");
    return null;
  }
  if (t.type === "doubles") {
    // The players without a partner are paired at random.
    const paired = new Set(draft.pairs.flat());
    const alone = byRank(draft.playerIds, rankOf(t.league_id)).filter(
      (id) => !paired.has(id),
    );
    if (alone.length < 2) {
      // FR-033: nothing to pair; the counter and the seeds stay.
      return fail(422, "nothing_to_pair", { unpaired: alone.length });
    }
    const rest = shuffled(alone, rngFor(t, draft.drawCounter + 1));
    for (let i = 0; i + 1 < rest.length; i += 2) {
      draft.pairs.push([rest[i] ?? "", rest[i + 1] ?? ""]);
    }
    rebuildEntries(t, draft, "draw");
    return null;
  }
  if (t.type !== "dyp") {
    return typeChanged(t);
  }
  const problem = dypDrawProblem(draft);
  if (problem) {
    return problem;
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

/**
 * What "Generate and start" would create, or why it would not: the backend's
 * `GET …/setup/preview` (FR-035). Like the backend it names the refusal the
 * start would give instead of a schedule, and it writes nothing.
 */
export function preview(t: StoredTournament): SchedulePreview {
  const draft = draftOf(t);
  const problem =
    t.state === "setup"
      ? startProblem(t)
      : fail(409, "tournament_not_in_setup", { state: t.state });
  if (problem) {
    return {
      draw_counter: draft.drawCounter,
      can_start: false,
      problem: { code: problem.code, detail: problem.detail },
      rounds: [],
      match_count: null,
      round_count: null,
      bracket_size: null,
    };
  }
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
    draw_counter: draft.drawCounter,
    can_start: true,
    problem: null,
    rounds: shown,
    match_count: made.matchCount,
    round_count: made.roundCount,
    bracket_size: made.bracketSize,
  };
}

/**
 * The most entries a round robin is generated for; the backend's limit (FR-032).
 * FR-032 now says 256; the change is the #48 follow-up (issue to open after approval).
 */
export const MAX_ROUND_ROBIN_ENTRIES = 64;

/**
 * The reason the tournament cannot start, with the backend's codes (FR-032,
 * FR-033); null when it can. Unlike the backend, which generates only the
 * round robin so far, the demo starts every format.
 */
export function startProblem(t: StoredTournament): SetupFailure | null {
  const draft = draftOf(t);
  const entries = t.entries.filter((entry) => entry.stage === "main");
  if (t.type === "doubles") {
    const paired = new Set(entries.flatMap((entry) => entry.player_ids));
    const unpaired = draft.playerIds.filter((id) => !paired.has(id)).length;
    if (unpaired > 0) {
      return fail(422, "players_without_partner", { unpaired });
    }
  }
  const minimum =
    t.type === "monster_dyp"
      ? 4
      : draft.format.group_phase === "none" && draft.format.third_place_match
        ? 4
        : 2;
  if (entries.length < minimum) {
    return fail(422, "not_enough_entries", { minimum, given: entries.length });
  }
  return draft.format.group_phase === "round_robin" &&
    entries.length > MAX_ROUND_ROBIN_ENTRIES
    ? fail(422, "too_many_entries_for_round_robin", {
        limit: MAX_ROUND_ROBIN_ENTRIES,
      })
    : null;
}

export function start(
  t: StoredTournament,
  expectedCounter: number,
): SetupFailure | null {
  const draft = draftOf(t);
  if (t.state !== "setup") {
    return fail(409, "tournament_not_in_setup", { state: t.state });
  }
  if (draft.drawCounter !== expectedCounter) {
    return fail(409, "draw_counter_changed", {
      draw_counter: draft.drawCounter,
    });
  }
  const problem = startProblem(t);
  if (problem) {
    return problem;
  }
  const phase = t.phases[0];
  if (!phase) {
    return fail(422, "format_not_supported");
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

/**
 * FR-036: back to setup is possible while no match in the tournament has a
 * result (BR-096): until the first result is entered, and again once every
 * result is cleared (FR-053). This demo counts the matches with an outcome.
 */
export function backToSetup(t: StoredTournament): SetupFailure | null {
  if (t.state !== "in_progress") {
    return fail(409, "tournament_not_in_progress", { state: t.state });
  }
  const results = t.rounds
    .flatMap((round) => round.matches)
    .filter((match) => match.outcome !== null).length;
  if (results > 0) {
    return fail(422, "tournament_has_results", { results });
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
    return fail(409, "season_closed");
  }
  const state = db();
  state.tournaments = state.tournaments.filter((other) => other.id !== t.id);
  return null;
}
