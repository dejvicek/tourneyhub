// What the play screens read from a tournament: names, rounds, fields and
// the waiting order. Presentation only; standings, placements and the
// waiting order come from the API (ADR-009).
import type { SkipToken } from "@tanstack/react-query";

import type {
  EntryRead,
  FieldRead,
  MatchFormat,
  MatchSideRead,
  PhaseRead,
  Player,
  PlayRead,
  Side,
} from "@/demo/contract";
import { matchFormat } from "@/features/results/matchFormat";
import type { tournamentQueries } from "@/features/tournaments/api";

/** The tournament as the client returns it (its sides are an array, not a pair). */
type DetailQueryFn = Exclude<
  ReturnType<typeof tournamentQueries.detail>["queryFn"],
  SkipToken | undefined
>;
export type TournamentData = Awaited<ReturnType<DetailQueryFn>>;
export type RoundData = TournamentData["rounds"][number];
export type MatchData = RoundData["matches"][number];

export interface MatchInfo {
  match: MatchData;
  round: RoundData;
  phase: PhaseRead;
  format: MatchFormat;
  /** The field the match is on, if any. */
  field: FieldRead | undefined;
  /** 1-based place in the waiting list, if it waits (FR-092). */
  queue: number | undefined;
}

export interface PlayModel {
  tournament: TournamentData;
  group: PhaseRead | undefined;
  knockout: PhaseRead | undefined;
  entries: ReadonlyMap<string, EntryRead>;
  /** Group-phase rounds in round order. */
  groupRounds: RoundData[];
  matches: ReadonlyMap<string, MatchInfo>;
  fields: FieldRead[];
  /** Waiting matches in the order they get a field. */
  waiting: PlayRead["waiting"];
  players: ReadonlyMap<string, string>;
}

/** "Anna Nováková" → "Anna N." as the design writes names on matches. */
export function shortName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  const first = parts[0] ?? fullName;
  const last = parts.length > 1 ? parts.at(-1) : undefined;
  return last === undefined ? first : `${first} ${last.charAt(0)}.`;
}

export function firstName(fullName: string): string {
  return fullName.trim().split(/\s+/)[0] ?? fullName;
}

export function buildModel(
  tournament: TournamentData,
  players: readonly Player[],
  play: PlayRead | undefined,
): PlayModel {
  const group = tournament.phases.find((phase) => phase.kind === "group");
  const knockout = tournament.phases.find((p) => p.kind === "knockout");
  const fields = [...tournament.fields].sort((a, b) => a.number - b.number);
  const waiting =
    play?.waiting ??
    tournament.waiting.map((match_id) => ({ match_id, busy: [] }));
  const queue = new Map(waiting.map((w, i) => [w.match_id, i + 1]));
  const matches = new Map<string, MatchInfo>();
  for (const phase of tournament.phases) {
    const phaseRounds = tournament.rounds
      .filter((round) => round.phase_id === phase.id)
      .sort((a, b) => a.round_no - b.round_no);
    for (const round of phaseRounds) {
      for (const match of round.matches) {
        matches.set(match.id, {
          match,
          round,
          phase,
          format: matchFormat(tournament, match.id) ?? phase.match_format,
          field: fields.find((field) => field.match_id === match.id),
          queue: queue.get(match.id),
        });
      }
    }
  }
  return {
    tournament,
    group,
    knockout,
    entries: new Map(tournament.entries.map((entry) => [entry.id, entry])),
    groupRounds: tournament.rounds
      .filter((round) => round.phase_id === group?.id)
      .sort((a, b) => a.round_no - b.round_no),
    matches,
    fields,
    waiting,
    players: new Map(players.map((player) => [player.id, player.name])),
  };
}

const NO_SIDE: MatchSideRead = {
  entry_id: null,
  player_ids: [],
  is_bye: false,
};

/** A match's two sides; the API always sends two. */
export function sidesOf(match: MatchData): [MatchSideRead, MatchSideRead] {
  return [match.sides[0] ?? NO_SIDE, match.sides[1] ?? NO_SIDE];
}

/** The full names of a side's players, in their order. */
export function sideNames(
  model: PlayModel,
  side: Pick<MatchSideRead, "player_ids">,
): string[] {
  return side.player_ids.map((id) => model.players.get(id) ?? "?");
}

export function entryPlayers(model: PlayModel, entryId: string): string[] {
  return sideNames(model, {
    player_ids: model.entries.get(entryId)?.player_ids ?? [],
  });
}

/** The side that won, or null for a draw or no result. */
export function winnerOf(match: MatchData): Side | null {
  return match.outcome === "side_1" || match.outcome === "side_2"
    ? match.outcome
    : null;
}

/** Games won by each side. */
export function gamesWon(match: MatchData): [number, number] {
  let a = 0;
  let b = 0;
  for (const game of match.games) {
    if (game.winner === "side_1") {
      a += 1;
    } else if (game.winner === "side_2") {
      b += 1;
    }
  }
  return [a, b];
}

/** The score shown for a played match: goals in BO1, games won otherwise. */
export function scoreOf(
  info: Pick<MatchInfo, "match" | "format">,
): [number, number] | null {
  const { match, format } = info;
  if (match.outcome === null || match.is_walkover) {
    return null;
  }
  if (format === "bo1") {
    const game = match.games[0];
    return game?.score_1 != null && game.score_2 != null
      ? [game.score_1, game.score_2]
      : null;
  }
  return gamesWon(match);
}

export interface Progress {
  played: number;
  total: number;
  /** The first round with a match still to play; null when all are played. */
  currentRound: number | null;
  rounds: number;
}

/** How far the group phase is (screen 6). */
export function groupProgress(model: PlayModel): Progress {
  const matches = model.groupRounds.flatMap((round) => round.matches);
  const current = model.groupRounds.find((round) =>
    round.matches.some((match) => match.outcome === null),
  );
  return {
    played: matches.filter((match) => match.outcome !== null).length,
    total: matches.length,
    currentRound: current?.round_no ?? null,
    rounds: model.groupRounds.length,
  };
}
