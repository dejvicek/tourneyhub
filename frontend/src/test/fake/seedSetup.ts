// The setup area's addition to the seed (ids 1000–1999): next week's DYP,
// still in setup, with 14 players picked and seven pairs drawn, so that
// screens 3–5 open on data and "Generate and start" can be tried from the
// tournament list.
import { demoId } from "./ids";
import type { SeedPart } from "./seed";

/** The date `days` after a YYYY-MM-DD date. */
function addDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T12:00:00`);
  date.setDate(date.getDate() + days);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export const seedSetup: SeedPart = {
  area: "setup",
  add(state, kit) {
    const t = kit.tournament(1000, {
      name: "Next Thursday DYP",
      date: addDays(kit.today, 7),
      type: "dyp",
      state: "setup",
    });
    t.phase(kit.roundRobinPhase);
    // The first 14 players of the roster: the top seven with the bottom seven.
    const players = Array.from({ length: 14 }, (_, i) => demoId(100 + i));
    for (let i = 0; i < 7; i++) {
      t.entry([players[i] ?? "", players[13 - i] ?? ""], i + 1);
    }
    t.fields(2);
    state.tournaments.push(t.tournament);
  },
};
