import type { MatchFormat, MatchRead, PhaseRead } from "@/demo/contract";

/** The parts of a tournament (TournamentRead) that decide a match's format. */
interface Bracket {
  phases: readonly PhaseRead[];
  rounds: readonly {
    phase_id: string;
    matches: readonly Pick<MatchRead, "id" | "kind">[];
  }[];
}

/**
 * The format a match is played in (BR-120): its phase's, except the final
 * of a knockout, which may have its own. The final is the standard match of
 * the bracket's round with only one (DATA-MODEL D4). Undefined for a match
 * the tournament does not have.
 */
export function matchFormat(
  tournament: Bracket,
  matchId: string,
): MatchFormat | undefined {
  const round = tournament.rounds.find((r) =>
    r.matches.some((match) => match.id === matchId),
  );
  const phase = tournament.phases.find((p) => p.id === round?.phase_id);
  const match = round?.matches.find((m) => m.id === matchId);
  if (round === undefined || phase === undefined || match === undefined) {
    return undefined;
  }
  const isFinal =
    phase.kind === "knockout" &&
    match.kind === "standard" &&
    round.matches.filter((m) => m.kind === "standard").length === 1;
  return (isFinal ? phase.final_match_format : null) ?? phase.match_format;
}
