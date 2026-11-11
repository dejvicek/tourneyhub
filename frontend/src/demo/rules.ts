// The rules the product team has not settled yet (GitHub issue #24). Each
// value below is what PRD.md says today; the comment names the rule and the
// proposal in the issue. Screens and demo handlers read these values instead
// of hard-coding them, so a decision changes one line here.
//
// The engine in the backend decides the real behaviour; these values only
// keep the demo and the screens consistent until it does.

export const RULES_ISSUE = "https://github.com/dejvicek/tourneyhub/issues/24";

/** BR-051: the order in which round-robin rounds are played. */
export type RoundRobinOrder =
  /** PRD: unspecified; the demo plays the circle method's rounds in order. */
  | "circle"
  /** Issue #24: reverse the circle rounds, so seeds 1 and 2 meet last. */
  | "top_seeds_last";

/** BR-058, BR-063: who sits out when the entries do not divide evenly. */
export type SitOutRule =
  /** PRD: fewest sit-outs first, then the lowest placed (Swiss) or by lot (Monster DYP). */
  | "fewest_sit_outs"
  /** Issue #24: the same, and never twice in a row while it can be avoided. */
  | "fewest_sit_outs_not_twice_in_a_row";

/** BR-101 (round robin), FR-043 (Swiss and Monster DYP): tie-breakers. */
export type RoundRobinTiebreaker =
  | "head_to_head"
  | "score_difference"
  /** Issue #24 proposes a game-difference step for BO3 and BO5. */
  | "game_difference";
export type SwissTiebreaker = "bh1" | "bh2" | "score_difference";

/** BR-092: when the score of every game is required. */
export type GameScoreRequirement =
  /** PRD: every game of a Swiss or Monster DYP round, except walkovers. */
  | "swiss_and_monster_dyp"
  /** Issue #24: only when score difference is an enabled tie-breaker. */
  | "when_score_difference_counts";

/** BR-081–BR-084: the knockout modes after Monster DYP rounds. */
export const MONSTER_KNOCKOUT_MODES = [
  "seeded_pairs",
  "singles",
  "a_little_mercy",
  // Issue #24: Kickertool uses "Lord have mercy" for a different knockout;
  // the proposal renames ours, e.g. to "Random pairs".
  "lord_have_mercy",
] as const;
export type MonsterKnockoutMode = (typeof MONSTER_KNOCKOUT_MODES)[number];

export interface Rules {
  roundRobinOrder: RoundRobinOrder;
  sitOuts: SitOutRule;
  topPlayersSitOutExempt: boolean;
  roundRobinTiebreakers: readonly RoundRobinTiebreaker[];
  swissTiebreakers: readonly SwissTiebreaker[];
  gameScoresRequired: GameScoreRequirement;
  monsterKnockoutModes: readonly MonsterKnockoutMode[];
}

// Annotated rather than `satisfies`: code branches on each union, which a
// literal type would rule out.
export const rules: Readonly<Rules> = {
  /** BR-051. Issue #24 proposes "top_seeds_last". */
  roundRobinOrder: "circle",

  /** BR-058, BR-063. Issue #24 proposes "fewest_sit_outs_not_twice_in_a_row". */
  sitOuts: "fewest_sit_outs",

  /**
   * FR-041, BR-061, BR-063: whether top players are exempt from the sit-out
   * lot in rounds 1 and 2. BR-063 as written exempts nobody; issue #24
   * proposes the same and closes the open question.
   */
  topPlayersSitOutExempt: false,

  /**
   * BR-101: after points, a round robin ranks two level entries by their
   * matches against each other, then by score difference, and then they share
   * the place. Issue #24 proposes Kickertool's order: points, encounter,
   * game and goal difference, and only then the direct comparison.
   */
  roundRobinTiebreakers: ["head_to_head", "score_difference"],

  /** FR-043: the default tie-breakers of a Swiss or Monster DYP, in order. */
  swissTiebreakers: ["bh1", "bh2", "score_difference"],

  /** BR-092. Issue #24 proposes "when_score_difference_counts". */
  gameScoresRequired: "swiss_and_monster_dyp",

  /**
   * FR-045, BR-081–BR-084: the modes offered, in this order. Their names are
   * the `knockoutModes` texts in src/i18n, the same in English and Czech
   * (FR-080), so a rename changes those texts.
   */
  monsterKnockoutModes: MONSTER_KNOCKOUT_MODES,
};

// Settled rules the demo also needs, from PRD.md, kept here so that the
// handlers and screens share them.
/** BR-070, BR-122: group-phase points for a win, a draw and a loss. */
export const MATCH_POINTS = { win: 2, draw: 1, loss: 0 } as const;
/** FR-011: the default placement points table, 1st to 5th. */
export const DEFAULT_PLACEMENT_POINTS = [10, 8, 6, 4, 2] as const;

// BR-071: only Swiss and Monster DYP score a sit-out, not a round robin. The
// points for sitting out default to 0 (FR-039, DEFAULT_SIT_OUT_POINTS in
// `@/lib/sitOutPoints`); the organizer picks 0, 1 or 2 in setup (BR-075).
