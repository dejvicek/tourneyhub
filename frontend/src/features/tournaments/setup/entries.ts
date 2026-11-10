import type { SetupData } from "./SetupPage";

/** The entries of the first phase in seed order. */
export function seededEntries(data: SetupData) {
  return data.setup.entries
    .filter((entry) => entry.stage === "main")
    .sort((a, b) => (a.seed ?? 0) - (b.seed ?? 0));
}
