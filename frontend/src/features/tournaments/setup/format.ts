import type { components } from "@/api/schema";

type Schemas = components["schemas"];
export type TournamentType = Schemas["TournamentType"];
export type MatchFormat = Schemas["MatchFormat"];
export type KnockoutMatchFormat = Schemas["KnockoutMatchFormat"];
export type GroupPhase = Schemas["GroupPhase"];
export type FormatWrite = Schemas["TournamentFormatWrite"];
type FormatRead = Schemas["TournamentFormatRead"];

/**
 * The format step's state: every setting has a value, also the settings the
 * chosen phases do not use, so that switching the group phase back and forth
 * keeps them. Only the final's format may be null ("same as the knockout").
 */
export type FormatForm = {
  [K in keyof FormatWrite]-?: K extends "final_match_format"
    ? FormatWrite[K]
    : NonNullable<FormatWrite[K]>;
};

/** The stored format with the unused settings filled in (FR-031). */
export function formOf(
  read: FormatRead,
  defaultFormat: KnockoutMatchFormat,
): FormatForm {
  return {
    ...read,
    round_robin_legs: read.round_robin_legs ?? 1,
    sit_out_points: read.sit_out_points ?? 0,
    group_match_format: read.group_match_format ?? defaultFormat,
    knockout_match_format: read.knockout_match_format ?? defaultFormat,
    third_place_match: read.third_place_match ?? false,
  };
}

/**
 * The target state the API takes: the group phase's settings with a group
 * phase, the knockout's without one, and null for the rest (FR-031, FR-045).
 */
export function writeOf(form: FormatForm): FormatWrite {
  const grouped = form.group_phase !== "none";
  return {
    ...form,
    round_robin_legs:
      form.group_phase === "round_robin" ? form.round_robin_legs : null,
    sit_out_points: grouped ? form.sit_out_points : null,
    group_match_format: grouped ? form.group_match_format : null,
    knockout_match_format: grouped ? null : form.knockout_match_format,
    final_match_format: grouped ? null : form.final_match_format,
    third_place_match: grouped ? null : form.third_place_match,
  };
}
