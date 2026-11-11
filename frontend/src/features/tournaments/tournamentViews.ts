// Which screen a tournament opens on and which tabs its header shows, from
// its state, current phase and format (the Figma file's "Tournament
// lifecycle" page, src/lib/paths.ts).
import type { components } from "@/api/schema";
import type { paths } from "@/lib/paths";

/**
 * What decides a tournament's screens: the season list's summary, or the
 * whole tournament the running screens read.
 */
export type TournamentView = Omit<
  components["schemas"]["TournamentSummary"],
  "player_count" | "progress" | "winner_player_ids"
>;

/** A screen of one tournament, without a match: a key of `paths`. */
export type TournamentScreen = keyof typeof paths &
  (
    | "setupPlayers"
    | "schedule"
    | "fields"
    | "tournamentStandings"
    | "groupPhaseDone"
    | "knockout"
    | "startKnockout"
    | "finished"
    | "betweenRounds"
    | "lateAndDisabled"
  );

function currentPhase(t: TournamentView) {
  return t.phases.find((phase) => phase.id === t.current_phase_id);
}

function groupFormat(t: TournamentView) {
  return t.phases.find((phase) => phase.kind === "group")?.format;
}

/** The screen that `tournament`, the tournament's own path, redirects to. */
export function tournamentHome(t: TournamentView): TournamentScreen {
  if (t.state === "setup") {
    return "setupPlayers";
  }
  if (t.state === "finished") {
    return "finished";
  }
  const phase = currentPhase(t) ?? t.phases[0];
  if (phase === undefined || phase.kind === "knockout") {
    return "knockout";
  }
  // Swiss and Monster DYP rounds always open on screen 11, done or not: it
  // offers another round, the knockout (13) and the finish.
  return phase.format === "round_robin"
    ? t.current_phase_done
      ? "groupPhaseDone"
      : "schedule"
    : "betweenRounds";
}

export interface TournamentTab {
  path: TournamentScreen;
  label:
    | "places"
    | "schedule"
    | "rounds"
    | "knockout"
    | "fields"
    | "players"
    | "standings";
}

/**
 * The header's tabs; none in setup. A round robin shows Fields, Schedule
 * and Standings (the design's order); Swiss and Monster DYP show Rounds, Fields, Players and
 * Standings. A knockout adds its tab once it exists, a finished tournament
 * its places first, and Fields and Players leave once nothing is played.
 */
export function tournamentTabs(t: TournamentView): TournamentTab[] {
  if (t.state === "setup") {
    return [];
  }
  const running = t.state === "in_progress";
  const group = groupFormat(t);
  const inGroup = currentPhase(t)?.kind !== "knockout";
  const hasKnockout = t.phases.some((phase) => phase.kind === "knockout");
  const tabs: TournamentTab[] = [];
  if (!running) {
    tabs.push({ path: "finished", label: "places" });
  }
  if (group === "round_robin") {
    // The design's order for a round robin: Fields, Schedule, Standings.
    if (running) {
      tabs.push({ path: "fields", label: "fields" });
    }
    tabs.push({ path: "schedule", label: "schedule" });
  } else if (group !== undefined) {
    tabs.push({ path: "betweenRounds", label: "rounds" });
  }
  if (hasKnockout) {
    tabs.push({ path: "knockout", label: "knockout" });
  }
  if (running && group !== "round_robin") {
    tabs.push({ path: "fields", label: "fields" });
  }
  if (running && inGroup && group !== undefined && group !== "round_robin") {
    tabs.push({ path: "lateAndDisabled", label: "players" });
  }
  tabs.push({ path: "tournamentStandings", label: "standings" });
  return tabs;
}
