// demo only, the engine decides
//
// The demo's tournaments for the finals screens (9–13): a DYP evening with
// its knockout under way, a Monster DYP of 15 players after round 5, a Swiss
// after round 3, and two knockouts without a group phase (8 and 16 spots,
// with byes). Added to the seed by seed.ts.
import type { MatchRead, PhaseRead, RoundRead } from "./contract";
import {
  createRng,
  drawDypPairs,
  randomGame,
  roundRobinRounds,
  roundRobinStandings,
} from "./engine";
import {
  drawKnockoutRounds,
  drawNextRound,
  rankingOf,
  roundFromDraw,
  roundsOf,
  setNote,
  syncBracket,
} from "./finalsEngine";
import { rules } from "./rules";
import type { SeedKit, SeedPart, StoredPlayer, StoredTournament } from "./seed";

/** The kit's builder, with ids as a plain function (the engine takes one). */
type Builder = ReturnType<SeedKit["tournament"]>;

function required<T>(value: T | undefined): T {
  if (value === undefined) {
    throw new Error("The finals seed is inconsistent");
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
  const games: MatchRead["games"] = [];
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

const at = (date: string, time: string) => `${date}T${time}:00Z`;

const GROUP_BASE: Omit<PhaseRead, "id" | "position"> = {
  kind: "group",
  format: "round_robin",
  round_robin_legs: 1,
  // BR-071: a round robin keeps no sit-out points.
  sit_out_points: null,
  sit_out_points_set_by_hand: false,
  tiebreakers: null,
  qualifiers: null,
  third_place_match: null,
  monster_knockout_mode: null,
  match_format: "bo1",
  final_match_format: null,
};

const KNOCKOUT_BASE: Omit<PhaseRead, "id" | "position"> = {
  ...GROUP_BASE,
  kind: "knockout",
  format: "single_elimination",
  round_robin_legs: null,
  sit_out_points: null,
  third_place_match: false,
  final_match_format: "bo3",
};

/** Plays every match of the round that has both sides. */
function playRound(
  round: RoundRead,
  t: StoredTournament,
  rng: () => number,
  date: string,
): void {
  for (const match of round.matches) {
    if (
      match.outcome === null &&
      match.sides.every((s) => s.player_ids.length > 0)
    ) {
      play(match, rng, t.goals_per_game, 1, at(date, "20:00"));
    }
  }
}

/** FR-044, FR-040: a Swiss or Monster DYP with `roundCount` rounds played. */
function groupRounds(args: {
  b: Builder;
  phase: PhaseRead;
  roundCount: number;
  rng: () => number;
  date: string;
  between?: (roundNo: number) => void;
}): void {
  const { b, phase, roundCount, rng, date, between } = args;
  for (let roundNo = 1; roundNo <= roundCount; roundNo++) {
    between?.(roundNo);
    const round = roundFromDraw({
      ids: () => b.id(),
      phaseId: phase.id,
      roundNo,
      drawn: drawNextRound(b.tournament),
    });
    b.tournament.rounds.push(round);
    playRound(round, b.tournament, rng, date);
  }
}

/** Screen 9: a DYP evening, round robin done, semifinals played, the BO3 final ready. */
function dypEvening(players: StoredPlayer[], kit: SeedKit): StoredTournament {
  const date = "2026-10-22";
  const rng = createRng(2210);
  const b = kit.tournament(3200, {
    name: "DYP evening",
    date,
    type: "dyp",
    state: "in_progress",
  });
  const group = b.phase(GROUP_BASE);
  const knockout = b.phase({ ...KNOCKOUT_BASE, qualifiers: 4 });
  const { pairs } = drawDypPairs(
    players.slice(0, 12).map((p) => p.id),
    rng,
  );
  const entries = pairs.map((pair, i) => b.entry(pair, i + 1));
  for (const pairing of roundRobinRounds(entries)) {
    const round = roundFromDraw({
      ids: () => b.id(),
      phaseId: group.id,
      roundNo: roundsOf(b.tournament, group).length + 1,
      drawn: {
        matches: pairing.matches.map(([x, y]) => [
          { entry_id: x.id, player_ids: x.player_ids, is_bye: false },
          { entry_id: y.id, player_ids: y.player_ids, is_bye: false },
        ]),
        sitting_out: pairing.sittingOut.map((e) => e.id),
      },
    });
    b.tournament.rounds.push(round);
    playRound(round, b.tournament, rng, date);
  }
  const order = roundRobinStandings(
    entries.map((e) => e.id),
    b.tournament.rounds,
  ).map((row) => required(entries.find((e) => e.id === row.entry_id)));
  b.tournament.rounds.push(
    ...drawKnockoutRounds({
      ids: () => b.id(),
      phaseId: knockout.id,
      seeded: order.slice(0, 4),
      thirdPlace: false,
    }),
  );
  const [semifinals] = roundsOf(b.tournament, knockout);
  playRound(required(semifinals), b.tournament, rng, date);
  syncBracket(b.tournament);
  b.fields(2);
  const final = required(roundsOf(b.tournament, knockout)[1]?.matches[0]);
  required(b.tournament.fields[0]).match_id = final.id;
  return b.tournament;
}

/** Screens 11–13: Monster DYP, 15 players, one joined in round 2, one disabled from round 4. */
function monsterDyp(players: StoredPlayer[], kit: SeedKit): StoredTournament {
  const date = "2026-11-05";
  const rng = createRng(1105);
  const b = kit.tournament(3300, {
    name: "Monster DYP",
    date,
    type: "monster_dyp",
    state: "in_progress",
  });
  const phase = b.phase({
    ...GROUP_BASE,
    format: "monster_dyp",
    round_robin_legs: null,
    // BR-071: Swiss and Monster DYP score a sit-out.
    sit_out_points: 0,
    sit_out_points_set_by_hand: true,
    // FR-043: the default order, from the rules.
    tiebreakers: [...rules.swissTiebreakers],
    qualifiers: 8,
    final_match_format: "bo3",
  });
  // The league ranking seeds round 1 (BR-060); the 15th player comes late.
  players.slice(0, 14).forEach((p, i) => b.entry([p.id], i + 1));
  b.fields(2);
  groupRounds({
    b,
    phase,
    roundCount: 5,
    rng,
    date,
    between: (roundNo) => {
      if (roundNo === 2) {
        const late = b.entry([required(players[14]).id], 15);
        setNote(b.tournament, late.id, { joined_round: 2 });
      }
      if (roundNo === 4) {
        // Disable a player in the top places, so the knockout notice shows.
        const row = required(rankingOf(b.tournament).rows[0]);
        const entry = required(
          b.tournament.entries.find((e) => e.id === row.entry_id),
        );
        entry.is_disabled = true;
        setNote(b.tournament, entry.id, { disabled_since_round: 4 });
      }
    },
  });
  return b.tournament;
}

/** A Swiss of nine, three rounds played. */
function swiss(players: StoredPlayer[], kit: SeedKit): StoredTournament {
  const date = "2026-11-03";
  const rng = createRng(1103);
  const b = kit.tournament(3450, {
    name: "Swiss evening",
    date,
    type: "singles",
    state: "in_progress",
  });
  const phase = b.phase({
    ...GROUP_BASE,
    format: "swiss",
    round_robin_legs: null,
    sit_out_points: 0,
    sit_out_points_set_by_hand: true,
    tiebreakers: [...rules.swissTiebreakers],
    qualifiers: 4,
  });
  players.slice(0, 9).forEach((p, i) => b.entry([p.id], i + 1));
  b.fields(2);
  groupRounds({ b, phase, roundCount: 3, rng, date });
  return b.tournament;
}

/** A knockout without a group phase: `count` singles seeded by the league, `played` first-round results. */
function knockoutOnly(args: {
  kit: SeedKit;
  players: StoredPlayer[];
  base: number;
  name: string;
  date: string;
  count: number;
  thirdPlace: boolean;
  playedMatches: number;
  onFieldMatches: number;
}): StoredTournament {
  const { kit, players, count, date } = args;
  const rng = createRng(args.base);
  const b = kit.tournament(args.base, {
    name: args.name,
    date,
    type: "singles",
    state: "in_progress",
  });
  const knockout = b.phase({
    ...KNOCKOUT_BASE,
    qualifiers: count,
    third_place_match: args.thirdPlace,
  });
  const entries = players.slice(0, count).map((p, i) => b.entry([p.id], i + 1));
  b.tournament.rounds.push(
    ...drawKnockoutRounds({
      ids: () => b.id(),
      phaseId: knockout.id,
      seeded: entries,
      thirdPlace: args.thirdPlace,
    }),
  );
  b.fields(2);
  const open = required(roundsOf(b.tournament, knockout)[0]).matches.filter(
    (m) => m.outcome === null,
  );
  open.slice(0, args.playedMatches).forEach((match) => {
    play(match, rng, b.tournament.goals_per_game, 1, at(date, "19:30"));
  });
  const waiting = open.slice(
    args.playedMatches,
    args.playedMatches + args.onFieldMatches,
  );
  waiting.forEach((match, i) => {
    required(b.tournament.fields[i]).match_id = match.id;
  });
  syncBracket(b.tournament);
  return b.tournament;
}

/** Screen 8 to 13: a singles round robin whose group phase is done and whose knockout is not drawn yet. */
function roundRobinDone(
  players: StoredPlayer[],
  kit: SeedKit,
): StoredTournament {
  const date = "2026-11-07";
  const rng = createRng(1107);
  const b = kit.tournament(3800, {
    name: "Round robin night",
    date,
    type: "singles",
    state: "in_progress",
  });
  const group = b.phase(GROUP_BASE);
  const entries = players.slice(0, 6).map((p, i) => b.entry([p.id], i + 1));
  for (const pairing of roundRobinRounds(entries)) {
    const round = roundFromDraw({
      ids: () => b.id(),
      phaseId: group.id,
      roundNo: roundsOf(b.tournament, group).length + 1,
      drawn: {
        matches: pairing.matches.map(([x, y]) => [
          { entry_id: x.id, player_ids: x.player_ids, is_bye: false },
          { entry_id: y.id, player_ids: y.player_ids, is_bye: false },
        ]),
        sitting_out: pairing.sittingOut.map((e) => e.id),
      },
    });
    b.tournament.rounds.push(round);
    playRound(round, b.tournament, rng, date);
  }
  b.fields(2);
  return b.tournament;
}

/** The finals screens' tournaments, for the seed (ids 3000–3999). */
export const seedFinals: SeedPart = {
  area: "finals",
  add(state, kit) {
    const { players } = state;
    state.tournaments.push(
      dypEvening(players, kit),
      monsterDyp(players, kit),
      swiss(players, kit),
      knockoutOnly({
        kit,
        players,
        base: 3600,
        name: "Spring Cup",
        date: "2026-11-08",
        count: 6,
        thirdPlace: true,
        playedMatches: 1,
        onFieldMatches: 1,
      }),
      knockoutOnly({
        kit,
        players,
        base: 3700,
        name: "Grand Prix",
        date: "2026-11-09",
        count: 13,
        thirdPlace: false,
        playedMatches: 3,
        onFieldMatches: 2,
      }),
      roundRobinDone(players, kit),
    );
  },
};
