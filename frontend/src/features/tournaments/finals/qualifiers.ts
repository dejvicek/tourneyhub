import type { components } from "@/api/schema";

/**
 * How many entries go through to the knockout (FR-045, BR-080), for the cut
 * line: the group phase's number, else the knockout phase's. The backend
 * stores it only on a knockout row, which exists once the knockout is drawn
 * (DATA-MODEL §4); before that no phase has it and there is no line.
 */
export function qualifiersOf(
  phases: readonly Pick<
    components["schemas"]["PhaseRead"],
    "kind" | "qualifiers"
  >[],
): number | null {
  const of = (kind: "group" | "knockout") =>
    phases.find((phase) => phase.kind === kind)?.qualifiers ?? null;
  return of("group") ?? of("knockout");
}
