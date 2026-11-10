import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { DEMO_LEAGUE_ID } from "@/demo/ids";
import {
  allowDraws,
  axeViolations,
  createDraft,
  setupOf,
  tournamentsOfSeason,
} from "@/demo/setupTestHelpers";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";

const leagueId = DEMO_LEAGUE_ID;
const newTournament = generatePath(paths.newTournament, { leagueId });

describe("setup: format (screen 2)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("creates the tournament with the league's defaults and goes on to the players", async () => {
    const user = userEvent.setup();
    const view = renderAt(newTournament);

    const name = await screen.findByRole("textbox", { name: "Name" });
    expect(name).toHaveDisplayValue(/^DYP on \d+ \w+/);
    expect(screen.getByRole("radio", { name: /^DYP/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Round robin" })).toBeChecked();
    // The league's defaults: 2 fields, 10 goals, BO1; and no BO2 without draws.
    expect(screen.getByRole("group", { name: "Fields" })).toHaveTextContent(
      "2",
    );
    expect(
      screen.getByRole("group", { name: "Goals per game" }),
    ).toHaveTextContent("10");
    expect(
      screen.queryByRole("radio", { name: "BO2" }),
    ).not.toBeInTheDocument();

    // The name follows the type until it is typed over.
    await user.click(screen.getByRole("radio", { name: /^Doubles/ }));
    expect(name).toHaveDisplayValue(/^Doubles on /);
    await user.click(
      screen.getByRole("button", { name: "More goals per game" }),
    );
    await user.click(
      within(
        screen.getByRole("radiogroup", { name: "Round robin matches" }),
      ).getByRole("radio", { name: "BO3" }),
    );
    await user.click(
      screen.getByRole("switch", { name: "Points for sitting out" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Next: pick players" }),
    );

    await waitFor(() => {
      expect(view.state.location.pathname).toMatch(/\/setup\/players$/);
    });
    const created = (await tournamentsOfSeason()).at(-1);
    expect(created).toMatchObject({ type: "doubles", state: "setup" });
    const setup = await setupOf(created?.id ?? "");
    expect(setup.format).toMatchObject({
      type: "doubles",
      goals_per_game: 11,
      group_phase: "round_robin",
      sit_out_points: 1,
      group_match_format: "bo3",
      field_count: 2,
    });
    expect(view.state.location.pathname).toContain(created?.id);
  });

  it("adapts to the group phase and the type", async () => {
    const user = userEvent.setup();
    renderAt(newTournament);
    await screen.findByRole("textbox", { name: "Name" });

    await user.click(screen.getByRole("radio", { name: "None" }));
    expect(
      screen.queryByRole("switch", { name: "Points for sitting out" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: "Third-place match" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("radiogroup", { name: "Round robin matches" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /^Monster DYP/ }));
    expect(
      screen.queryByRole("radiogroup", { name: "Group phase" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Monster DYP plays its own rounds"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("radiogroup", { name: "Monster DYP matches" }),
    ).toBeInTheDocument();
  });

  it("offers BO2 in a league that allows draws", async () => {
    await allowDraws();
    renderAt(newTournament);

    expect(await screen.findByRole("radio", { name: "BO2" })).toBeVisible();
  });

  it("asks for a name before it creates anything", async () => {
    const user = userEvent.setup();
    const before = (await tournamentsOfSeason()).length;
    renderAt(newTournament);

    const name = await screen.findByRole("textbox", { name: "Name" });
    expect(name).not.toHaveAttribute("aria-invalid");
    await user.clear(name);
    await user.click(
      screen.getByRole("button", { name: "Next: pick players" }),
    );

    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(name).toHaveFocus();
    expect(name).toHaveAccessibleDescription(/Give the tournament a name\./);
    expect(await tournamentsOfSeason()).toHaveLength(before);
  });

  it("changes the tournament it was opened for instead of creating another", async () => {
    const user = userEvent.setup();
    const id = await createDraft({ name: "Friday DYP" });
    const before = (await tournamentsOfSeason()).length;
    const view = renderAt(`${newTournament}?tournament=${id}`);

    const name = await screen.findByRole("textbox", { name: "Name" });
    expect(name).toHaveValue("Friday DYP");
    await user.clear(name);
    await user.type(name, "Friday finals");
    await user.click(
      screen.getByRole("button", { name: "Next: pick players" }),
    );

    await waitFor(() => {
      expect(view.state.location.pathname).toMatch(/\/setup\/players$/);
    });
    const all = await tournamentsOfSeason();
    expect(all).toHaveLength(before);
    expect(all.find((t) => t.id === id)?.name).toBe("Friday finals");
  });

  it("shows its texts in Czech", async () => {
    await i18n.changeLanguage("cs");
    renderAt(newTournament);

    expect(
      await screen.findByRole("textbox", { name: "Název" }),
    ).toHaveDisplayValue(/^DYP, /);
    expect(
      screen.getByRole("button", { name: "Další: výběr hráčů" }),
    ).toBeInTheDocument();
  });

  it.each([
    ["phone", 390],
    ["desktop", 1280],
  ])("has no axe violations on a %s", async (_, width) => {
    stubViewport(width);
    renderAt(newTournament);
    await screen.findByRole("textbox", { name: "Name" });
    if (width > 1000) {
      expect(
        await screen.findByRole("heading", { name: "So far" }),
      ).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Cancel" })).toBeVisible();
    }

    expect(await axeViolations()).toEqual([]);
    expect(
      within(
        screen.getByRole("navigation", { name: "Setup steps" }),
      ).getAllByRole("listitem"),
    ).toHaveLength(4);
  });
});
