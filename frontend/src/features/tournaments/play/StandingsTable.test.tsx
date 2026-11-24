import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { components } from "@/api/schema";
import { i18n } from "@/i18n";

import type { PlayModel } from "./model";
import { StandingsTable } from "./StandingsTable";

type PlayStandingRow = components["schemas"]["PlayStandingRow"];

const ROW: PlayStandingRow = {
  ahead_by: null,
  bh1: null,
  bh2: null,
  drawn: 0,
  entry_id: "e1",
  form: [],
  game_difference: 2,
  lost: 0,
  place: 1,
  played: 1,
  points: 3,
  sat_out: 0,
  score_difference: 4,
  won: 1,
};

function modelOf(format: string, matchFormat: string): PlayModel {
  // eslint-disable-next-line no-restricted-syntax -- a stub: the table reads only these three fields
  return {
    group: { format, match_format: matchFormat },
    entries: new Map(),
    players: new Map(),
  } as unknown as PlayModel;
}

function renderTable(format: string, matchFormat: string) {
  render(
    <StandingsTable
      model={modelOf(format, matchFormat)}
      rows={[ROW]}
      caption="Standings"
    />,
  );
}

describe("StandingsTable game difference (BR-101, #92)", () => {
  it("shows the game-difference column in a BO3 round robin", async () => {
    await i18n.changeLanguage("en");
    renderTable("round_robin", "bo3");

    expect(
      screen.getByRole("columnheader", { name: "Game difference" }),
    ).toBeInTheDocument();
  });

  it.each(["swiss", "monster_dyp"])(
    "hides the game-difference column in a BO3 %s",
    async (format) => {
      await i18n.changeLanguage("en");
      renderTable(format, "bo3");

      expect(
        screen.queryByRole("columnheader", { name: "Game difference" }),
      ).not.toBeInTheDocument();
    },
  );
});
