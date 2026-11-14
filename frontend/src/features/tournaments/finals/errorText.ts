import type { TFunction } from "i18next";

import { ApiError, type ErrorCode } from "@/api/client";
import type { components } from "@/api/schema";

type KnockoutProblemRead = components["schemas"]["KnockoutProblemRead"];

/**
 * The refusals of the knockout's and the Swiss rounds' writes with a text of
 * their own (ADR-008; FR-040, FR-043, FR-046, FR-047, BR-065, BR-066).
 */
const CODE_TEXTS = {
  group_phase_not_done: "finals.errors.groupNotDone",
  qualifiers_out_of_range: "finals.errors.qualifiers",
  format_not_supported: "finals.errors.formatNotSupported",
  knockout_mode_not_applicable: "finals.errors.modeNotApplicable",
  phase_not_deletable: "finals.errors.phaseNotDeletable",
  season_closed: "finals.errors.seasonClosed",
  qualifiers_changed: "finals.errors.qualifiersChanged",
  match_has_result: "finals.errors.finalHasResult",
  round_number_changed: "finals.errors.roundNumberChanged",
  round_not_complete: "finals.errors.roundNotComplete",
  round_not_newest: "finals.errors.roundNotNewest",
  not_enough_entries: "finals.errors.notEnoughEntries",
  not_enough_players: "finals.errors.notEnoughPlayers",
  group_phase_locked: "finals.errors.groupPhaseLocked",
  knockout_mode_required: "finals.errors.modeRequired",
  qualifiers_odd: "finals.errors.qualifiersOdd",
  late_entry_not_allowed: "finals.errors.lateEntryNotAllowed",
  player_already_in_tournament: "finals.errors.playerAlreadyInTournament",
} as const satisfies Partial<Record<ErrorCode, string>>;

function hasText(code: ErrorCode | undefined): code is keyof typeof CODE_TEXTS {
  return code !== undefined && code in CODE_TEXTS;
}

function textFor(
  t: TFunction,
  code: ErrorCode | undefined,
  detail: Record<string, unknown>,
): string | null {
  if (!hasText(code)) {
    return null;
  }
  return t(CODE_TEXTS[code], {
    minimum: Number(detail.minimum),
    maximum: Number(detail.maximum),
  });
}

/** Why the preview says the knockout cannot start (FR-045, BR-080). */
export function problemText(
  t: TFunction,
  problem: KnockoutProblemRead,
): string {
  return textFor(t, problem.code, problem.detail) ?? t("finals.common.refused");
}

/** What a failed write says: 409 and 404 mean the data changed and was reloaded (ADR-008). */
export function errorText(t: TFunction, error: unknown): string {
  if (error instanceof ApiError) {
    const text = textFor(t, error.code, error.detail);
    if (text !== null) {
      return text;
    }
    if (error.status === 409 || error.status === 404) {
      return t("finals.common.stale");
    }
    if (error.status === 422) {
      return t("finals.common.refused");
    }
  }
  return t("finals.common.failed");
}

/**
 * What a failed finish says (FR-040), the same after the round robin and
 * between the rounds: a 409 means it changed and was reloaded (ADR-008).
 */
export function finishErrorText(t: TFunction, error: unknown): string {
  return error instanceof ApiError && error.status === 409
    ? t("roundRobin.done.finishChanged")
    : t("roundRobin.done.finishFailed");
}
