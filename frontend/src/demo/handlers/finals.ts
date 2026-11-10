// Demo handlers: the finals of a tournament (FR-037, FR-040–FR-048): the
// knockout bracket and places, rounds of a Swiss or Monster DYP, late and
// disabled players, tie-breakers, finishing, and starting or deleting the
// knockout. The logic is finalsEngine.ts (`// demo only, the engine decides`).
// A write sends the target state, or the number it expects (ADR-008); an
// expectation that is stale answers 409, which the screens meet with a reload.
import type { BracketRead, MatchRead, ParticipantRead } from "../contract";
import { fillFields, waitingMatches } from "../engine";
import {
  bracketOf,
  drawKnockoutRounds,
  drawNextRound,
  groupPhase,
  highestIdNumber,
  knockoutPhase,
  need,
  participantsOf,
  placesOf,
  planKnockout,
  previewOf,
  rankingOf,
  roundFromDraw,
  roundsOf,
  setNote,
  syncBracket,
} from "../finalsEngine";
import { demoId } from "../ids";
import { apiError, route } from "../route";
import { MONSTER_KNOCKOUT_MODES, rules } from "../rules";
import type { StoredTournament } from "../seed";
import { db, findTournament, tournamentRead } from "../store";

interface Ids {
  league_id: string;
  tournament_id: string;
}

function notFound(ids: Ids) {
  return apiError(404, "not_found", { tournament_id: ids.tournament_id });
}

/** 409: the request expected a state the tournament no longer has (ADR-008). */
function stale(reason: string, expected: number, current: number) {
  return apiError(409, "bad_request", { reason, expected, current });
}

/** 422: the state refuses the request and a reload would change nothing. */
function refused(reason: string) {
  return apiError(422, "validation_failed", { reason });
}

function idFactory(): () => string {
  let n = highestIdNumber(db().tournaments);
  return () => {
    n += 1;
    return demoId(n);
  };
}

/** FR-094: waiting matches take the free fields. */
function refillFields(t: StoredTournament): void {
  const matches = new Map<string, MatchRead>(
    t.rounds.flatMap((round) => round.matches).map((m) => [m.id, m]),
  );
  t.fields = fillFields(t.fields, waitingMatches(t.rounds, t.fields), matches);
}

function roundIsComplete(t: StoredTournament): boolean {
  const group = groupPhase(t);
  const rounds = group ? roundsOf(t, group) : [];
  // A round robin has all its rounds from the start; the others have one at a time.
  const open = group?.format === "round_robin" ? rounds : rounds.slice(-1);
  return open.every((r) => r.matches.every((m) => m.outcome !== null));
}

function usesRounds(t: StoredTournament): boolean {
  const format = groupPhase(t)?.format;
  return format === "swiss" || format === "monster_dyp";
}

function participant(
  t: StoredTournament,
  entryId: string,
): ParticipantRead | undefined {
  return participantsOf(t).find((p) => p.entry_id === entryId);
}

function seasonTable(t: StoredTournament): number[] {
  return db().seasons.find((s) => s.id === t.season_id)?.placement_points ?? [];
}

export const finalsHandlers = [
  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/bracket",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params);
      }
      // Results are entered through the result route, which does not know the
      // bracket: the winners move on, and the tournament finishes, when read.
      syncBracket(t);
      return bracketOf(t) ?? apiError(404, "not_found", { knockout: "none" });
    },
  ),

  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/places",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params);
      }
      syncBracket(t);
      const detailed = placesOf(t, seasonTable(t));
      if (detailed) {
        return detailed;
      }
      // A plain round robin: the base engine's places.
      return {
        complete: t.state === "finished",
        rows: (tournamentRead(t).places ?? []).map((row) => ({
          ...row,
          reason: {
            kind: "group_place" as const,
            round: null,
            score: null,
            opponent_entry_id: null,
            group_place: row.place,
            group_format: "round_robin" as const,
          },
        })),
      };
    },
  ),

  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/ranking",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params);
      }
      return rankingOf(t);
    },
  ),

  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/participants",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      return t ? participantsOf(t) : notFound(params);
    },
  ),

  route(
    "post",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/rounds",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      const group = t ? groupPhase(t) : undefined;
      if (!t || !group) {
        return notFound(params);
      }
      const rounds = roundsOf(t, group);
      if (body.expected_round_no !== rounds.length + 1) {
        return stale("round_number", body.expected_round_no, rounds.length + 1);
      }
      if (!usesRounds(t) || knockoutPhase(t) || t.state !== "in_progress") {
        return refused("rounds_not_allowed");
      }
      if (!roundIsComplete(t)) {
        return refused("round_incomplete");
      }
      const drawn = drawNextRound(t);
      if (drawn.matches.length === 0) {
        return refused("too_few_players");
      }
      const round = roundFromDraw({
        ids: idFactory(),
        phaseId: group.id,
        roundNo: body.expected_round_no,
        drawn,
      });
      t.rounds.push(round);
      refillFields(t);
      return round;
    },
    201,
  ),

  route(
    "delete",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/rounds/{round_id}",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      const group = t ? groupPhase(t) : undefined;
      const round = t?.rounds.find((r) => r.id === params.round_id);
      if (!t || !group || round?.phase_id !== group.id) {
        return apiError(404, "not_found", { round_id: params.round_id });
      }
      const rounds = roundsOf(t, group);
      if (!usesRounds(t) || knockoutPhase(t)) {
        return refused("rounds_not_allowed");
      }
      if (rounds.at(-1)?.id !== round.id) {
        return stale("newest_round", round.round_no, rounds.length);
      }
      // BR-066: the newest round goes with its matches and results.
      const gone = new Set(round.matches.map((m) => m.id));
      t.rounds = t.rounds.filter((r) => r.id !== round.id);
      t.fields = t.fields.map((field) =>
        field.match_id !== null && gone.has(field.match_id)
          ? { ...field, match_id: null }
          : field,
      );
      if (round.round_no === 1) {
        t.state = "setup"; // FR-046
      }
      return null;
    },
  ),

  route(
    "post",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/entries",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      const group = t ? groupPhase(t) : undefined;
      if (!t || !group) {
        return notFound(params);
      }
      const next = roundsOf(t, group).length + 1;
      if (body.from_round_no !== next) {
        return stale("round_number", body.from_round_no, next);
      }
      // FR-047, BR-067: only Swiss and Monster DYP take late players here.
      if (!usesRounds(t) || knockoutPhase(t)) {
        return refused("late_entries_not_allowed");
      }
      const player = db().players.find(
        (p) =>
          p.id === body.player_id &&
          p.league_id === t.league_id &&
          p.removed_at === null,
      );
      if (!player) {
        return apiError(404, "not_found", { player_id: body.player_id });
      }
      if (t.entries.some((e) => e.player_ids.includes(player.id))) {
        return refused("already_playing");
      }
      const ids = idFactory();
      const entry = {
        id: ids(),
        stage: "main" as const,
        kind: "player" as const,
        seed: Math.max(0, ...t.entries.map((e) => e.seed ?? 0)) + 1,
        player_ids: [player.id],
        is_disabled: false,
        is_top_player: false,
      };
      t.entries.push(entry);
      setNote(t, entry.id, { joined_round: next });
      return need(participant(t, entry.id));
    },
    201,
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/entries/{entry_id}/disabled",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      const group = t ? groupPhase(t) : undefined;
      const entry = t?.entries.find(
        (e) => e.id === params.entry_id && e.stage === "main",
      );
      if (!t || !group || !entry) {
        return apiError(404, "not_found", { entry_id: params.entry_id });
      }
      if (!usesRounds(t) || knockoutPhase(t)) {
        return refused("disable_not_allowed");
      }
      if (entry.is_disabled !== body.disabled) {
        entry.is_disabled = body.disabled;
        setNote(t, entry.id, {
          disabled_since_round: body.disabled
            ? roundsOf(t, group).length + 1
            : null,
        });
      }
      return need(participant(t, entry.id));
    },
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/tiebreakers",
    ({ params, body }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      const group = t ? groupPhase(t) : undefined;
      if (!t || !group) {
        return notFound(params);
      }
      const offered: readonly string[] = rules.swissTiebreakers;
      const valid =
        usesRounds(t) &&
        new Set(body.tiebreakers).size === body.tiebreakers.length &&
        body.tiebreakers.every((tiebreaker) => offered.includes(tiebreaker));
      if (!valid) {
        return refused("tiebreakers");
      }
      group.tiebreakers = [...body.tiebreakers];
      return rankingOf(t);
    },
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/state",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t) {
        return notFound(params);
      }
      if (t.state !== "finished") {
        // FR-037: a knockout finishes by itself. FR-040: the rest is finished
        // by the organizer once the current round has its results.
        if (
          knockoutPhase(t) ||
          t.state !== "in_progress" ||
          !roundIsComplete(t)
        ) {
          return refused("cannot_finish");
        }
        t.state = "finished";
      }
      return tournamentRead(t);
    },
  ),

  route(
    "get",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout/preview",
    ({ params, url }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      if (!t || !groupPhase(t)) {
        return notFound(params);
      }
      const mode = url.searchParams.get("mode");
      const known = MONSTER_KNOCKOUT_MODES.find((m) => m === mode) ?? null;
      return previewOf({
        t,
        qualifiers: Number(url.searchParams.get("qualifiers") ?? 0),
        mode: known,
        draw: Number(url.searchParams.get("draw") ?? 0),
      });
    },
  ),

  route(
    "put",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout",
    ({ params, body }): BracketRead | Response => {
      const t = findTournament(params.league_id, params.tournament_id);
      const group = t ? groupPhase(t) : undefined;
      if (!t || !group) {
        return notFound(params);
      }
      const existing = bracketOf(t);
      if (existing) {
        // The target state is already there (a repeated request).
        return t.phases.find((p) => p.id === existing.phase_id)?.qualifiers ===
          body.qualifiers
          ? existing
          : stale("knockout_exists", body.qualifiers, 0);
      }
      if (t.state !== "in_progress" || !roundIsComplete(t)) {
        return refused("round_incomplete");
      }
      const monster = group.format === "monster_dyp";
      const mode = monster ? body.mode : null;
      if (
        monster &&
        (mode === null || !rules.monsterKnockoutModes.includes(mode))
      ) {
        return refused("mode");
      }
      const plan = planKnockout({
        t,
        qualifiers: body.qualifiers,
        mode,
        draw: body.draw,
      });
      // BR-080: at least 2 entries, or 4 with a third-place match.
      if (plan.entries.length < (body.third_place_match ? 4 : 2)) {
        return refused("too_few_entries");
      }
      const ids = idFactory();
      const phase = {
        id: ids(),
        position: t.phases.length + 1,
        kind: "knockout" as const,
        format: "single_elimination" as const,
        round_robin_legs: null,
        sit_out_points: null,
        tiebreakers: null,
        qualifiers: plan.qualifiers,
        third_place_match: body.third_place_match,
        monster_knockout_mode: mode,
        match_format:
          group.match_format === "bo2" ? ("bo1" as const) : group.match_format,
        final_match_format: group.final_match_format,
      };
      t.phases.push(phase);
      const mainById = new Map(t.entries.map((e) => [e.id, e]));
      const seeded = plan.entries.map((planned) => {
        const members = planned.member_ids.flatMap(
          (id) => mainById.get(id) ?? [],
        );
        if (mode === null) {
          return members[0];
        }
        const entry = {
          id: ids(),
          stage: "knockout" as const,
          kind: members.length === 1 ? ("player" as const) : ("pair" as const),
          seed: planned.seed,
          player_ids: members.flatMap((m) => m.player_ids),
          is_disabled: false,
          is_top_player: false,
        };
        t.entries.push(entry);
        return entry;
      });
      t.rounds.push(
        ...drawKnockoutRounds({
          ids,
          phaseId: phase.id,
          seeded: seeded.flatMap((entry) => entry ?? []),
          thirdPlace: body.third_place_match,
        }),
      );
      syncBracket(t);
      refillFields(t);
      return need(bracketOf(t));
    },
  ),

  route(
    "delete",
    "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/phases/{phase_id}",
    ({ params }) => {
      const t = findTournament(params.league_id, params.tournament_id);
      const phase = t ? knockoutPhase(t) : undefined;
      if (phase?.id !== params.phase_id || !t) {
        return apiError(404, "not_found", { phase_id: params.phase_id });
      }
      // BR-087: the group phase is unlocked and the organizer chooses again.
      const gone = new Set(
        t.rounds
          .filter((r) => r.phase_id === phase.id)
          .flatMap((r) => r.matches.map((m) => m.id)),
      );
      t.rounds = t.rounds.filter((r) => r.phase_id !== phase.id);
      t.phases = t.phases.filter((p) => p.id !== phase.id);
      t.entries = t.entries.filter((e) => e.stage !== "knockout");
      t.fields = t.fields.map((field) =>
        field.match_id !== null && gone.has(field.match_id)
          ? { ...field, match_id: null }
          : field,
      );
      t.state = "in_progress";
      return null;
    },
  ),
];
