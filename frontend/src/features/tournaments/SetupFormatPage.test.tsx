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
    // BR-071: a round robin has no points for sitting out.
    expect(
      screen.queryByRole("radiogroup", { name: "Points for sitting out" }),
    ).not.toBeInTheDocument();
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
      sit_out_points: null,
      sit_out_points_set_by_hand: false,
      group_match_format: "bo3",
      knockout_match_format: null,
      third_place_match: null,
      field_count: 2,
    });
    expect(view.state.location.pathname).toContain(created?.id);
  });

  it("adapts to the group phase and the type", async () => {
    const user = userEvent.setup();
    renderAt(newTournament);
    await screen.findByRole("textbox", { name: "Name" });

    // A knockout after a group phase is set up when it starts (FR-045).
    expect(
      screen.queryByRole("radiogroup", { name: "Knockout matches" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("radiogroup", { name: "Final" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "None" }));
    expect(
      screen.getByRole("radiogroup", { name: "Knockout matches" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("radiogroup", { name: "Points for sitting out" }),
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

  describe("points for sitting out in a league without draws (BR-071)", () => {
    it("defaults to 2, like a win, and says why", async () => {
      const user = userEvent.setup();
      renderAt(newTournament);
      await screen.findByRole("textbox", { name: "Name" });
      await user.click(screen.getByRole("radio", { name: "Swiss" }));

      expect(
        within(
          screen.getByRole("radiogroup", { name: "Points for sitting out" }),
        ).getByRole("radio", { name: "2 points (default)" }),
      ).toBeChecked();
      expect(
        screen.getByText(
          /The default is 2 points, like a win: no match in this league can end level\./,
        ),
      ).toBeVisible();
    });
  });

  describe("points for sitting out (FR-039, BR-071)", () => {
    beforeEach(async () => {
      await allowDraws();
    });

    const sitOut = () =>
      screen.getByRole("radiogroup", { name: "Points for sitting out" });
    const matches = () =>
      screen.getByRole("radiogroup", { name: "Swiss matches" });
    const chooseSwiss = async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(screen.getByRole("radio", { name: "Swiss" }));
    };

    it("is only for Swiss and Monster DYP, not for a round robin", async () => {
      const user = userEvent.setup();
      renderAt(newTournament);
      await screen.findByRole("textbox", { name: "Name" });
      expect(screen.getByRole("radio", { name: "Round robin" })).toBeChecked();
      expect(
        screen.queryByRole("radiogroup", { name: "Points for sitting out" }),
      ).not.toBeInTheDocument();

      await chooseSwiss(user);
      expect(sitOut()).toBeVisible();

      await user.click(screen.getByRole("radio", { name: "Round robin" }));
      expect(
        screen.queryByRole("radiogroup", { name: "Points for sitting out" }),
      ).not.toBeInTheDocument();

      await user.click(screen.getByRole("radio", { name: /^Monster DYP/ }));
      expect(sitOut()).toBeVisible();
    });

    it("offers 0, 1 and 2, with the default of the match format marked", async () => {
      const user = userEvent.setup();
      renderAt(newTournament);
      await screen.findByRole("textbox", { name: "Name" });
      await chooseSwiss(user);

      expect(
        within(sitOut())
          .getAllByRole("radio")
          .map(
            (radio) => radio.getAttribute("aria-label") ?? radio.textContent,
          ),
      ).toEqual(["0 points", "1 point (default)", "2 points"]);
      expect(
        within(sitOut()).getByRole("radio", { name: "1 point (default)" }),
      ).toBeChecked();
      expect(
        screen.getByText(/The default for BO1 matches: 1 point, like a draw\./),
      ).toBeVisible();
      expect(
        screen.queryByRole("button", { name: /^Use the default/ }),
      ).not.toBeInTheDocument();
    });

    it("names the options with their unit in Czech", async () => {
      const user = userEvent.setup();
      await i18n.changeLanguage("cs");
      renderAt(newTournament);
      await screen.findByRole("textbox", { name: "Název" });
      await user.click(screen.getByRole("radio", { name: "Švýcarský" }));

      expect(
        within(screen.getByRole("radiogroup", { name: "Body za volno" }))
          .getAllByRole("radio")
          .map((radio) => radio.textContent),
      ).toEqual(["0 bodů", "1 bod (výchozí)", "2 body"]);
    });

    it("follows the match format until the organizer picks a value", async () => {
      const user = userEvent.setup();
      renderAt(newTournament);
      await screen.findByRole("textbox", { name: "Name" });
      await chooseSwiss(user);

      await user.click(within(matches()).getByRole("radio", { name: "BO3" }));
      expect(
        within(sitOut()).getByRole("radio", { name: "2 points (default)" }),
      ).toBeChecked();
      expect(
        screen.getByText(/The default for BO3 matches: 2 points, like a win\./),
      ).toBeVisible();
      await user.click(within(matches()).getByRole("radio", { name: "BO1" }));

      expect(
        within(sitOut()).getByRole("radio", { name: "1 point (default)" }),
      ).toBeChecked();
    });

    it("keeps a picked value when the match format changes, and goes back to the default", async () => {
      const user = userEvent.setup();
      renderAt(newTournament);
      await screen.findByRole("textbox", { name: "Name" });
      await chooseSwiss(user);

      await user.click(
        within(sitOut()).getByRole("radio", { name: "0 points" }),
      );
      await user.click(within(matches()).getByRole("radio", { name: "BO5" }));

      expect(
        within(sitOut()).getByRole("radio", { name: "0 points" }),
      ).toBeChecked();
      expect(screen.getByText(/Set by you\./)).toBeVisible();
      expect(
        within(sitOut()).getByRole("radio", { name: "2 points (default)" }),
      ).not.toBeChecked();
      const reset = screen.getByRole("button", { name: "Use the default (2)" });
      await user.click(reset);

      expect(
        within(sitOut()).getByRole("radio", { name: "2 points (default)" }),
      ).toBeChecked();
      expect(
        screen.queryByRole("button", { name: /^Use the default/ }),
      ).not.toBeInTheDocument();
    });

    it("counts a click or Space or Enter on the checked default as a pick", async () => {
      const user = userEvent.setup();
      renderAt(newTournament);
      await screen.findByRole("textbox", { name: "Name" });
      await chooseSwiss(user);
      const reset = () =>
        screen.queryByRole("button", { name: /^Use the default/ });

      await user.click(
        within(sitOut()).getByRole("radio", { name: "1 point (default)" }),
      );
      expect(screen.getByText(/Set by you\./)).toBeVisible();
      await user.click(
        screen.getByRole("button", { name: /^Use the default/ }),
      );
      expect(reset()).not.toBeInTheDocument();

      for (const key of ["{Enter}", " "]) {
        within(sitOut())
          .getByRole("radio", { name: "1 point (default)" })
          .focus();
        await user.keyboard(key);
        expect(reset()).toBeInTheDocument();
        await user.click(
          screen.getByRole("button", { name: /^Use the default/ }),
        );
        expect(reset()).not.toBeInTheDocument();
      }
      expect(
        within(sitOut()).getByRole("radio", { name: "1 point (default)" }),
      ).toBeChecked();
    });

    it("saves a pick as the organizer's own", async () => {
      const user = userEvent.setup();
      const view = renderAt(newTournament);
      await screen.findByRole("textbox", { name: "Name" });
      await chooseSwiss(user);
      await user.click(
        within(sitOut()).getByRole("radio", { name: "2 points" }),
      );
      await user.click(
        screen.getByRole("button", { name: "Next: pick players" }),
      );
      await waitFor(() => {
        expect(view.state.location.pathname).toMatch(/\/setup\/players$/);
      });
      const picked = (await tournamentsOfSeason()).at(-1);

      expect((await setupOf(picked?.id ?? "")).format).toMatchObject({
        sit_out_points: 2,
        sit_out_points_set_by_hand: true,
      });
    });

    it("shows a stored pick and saves the way back to the default", async () => {
      const user = userEvent.setup();
      const id = await createDraft({ group_phase: "swiss", sit_out_points: 2 });
      const view = renderAt(`${newTournament}?tournament=${id}`);
      await screen.findByRole("textbox", { name: "Name" });
      expect(
        within(sitOut()).getByRole("radio", { name: "2 points" }),
      ).toBeChecked();

      await user.click(
        screen.getByRole("button", { name: "Use the default (1)" }),
      );
      await user.click(
        screen.getByRole("button", { name: "Next: pick players" }),
      );
      await waitFor(() => {
        expect(view.state.location.pathname).toMatch(/\/setup\/players$/);
      });

      expect((await setupOf(id)).format).toMatchObject({
        sit_out_points: 1,
        sit_out_points_set_by_hand: false,
      });
    });
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
