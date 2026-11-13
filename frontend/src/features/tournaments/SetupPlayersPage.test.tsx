import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { DEMO_LEAGUE_ID } from "@/test/fake/ids";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";
import {
  axeViolations,
  createDraft,
  pickPlayers,
  setupOf,
} from "@/test/setupTestHelpers";

const leagueId = DEMO_LEAGUE_ID;
const playersPage = (tournamentId: string) =>
  generatePath(paths.setupPlayers, { leagueId, tournamentId });

describe("setup: who is playing tonight (screen 3)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("picks players from the league ranking and saves them", async () => {
    const user = userEvent.setup();
    const id = await createDraft();
    const view = renderAt(playersPage(id));

    expect(
      await screen.findByRole("heading", { name: "0 of 16 picked" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Pick at least 4 players")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next: draw pairs" }),
    ).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Pick all" }));
    await user.click(
      screen.getByRole("checkbox", { name: /^Veronika Fialová/ }),
    );
    await user.click(screen.getByRole("checkbox", { name: /^Filip Šimek/ }));
    await user.click(screen.getByRole("checkbox", { name: /^David Beneš/ }));
    await user.click(screen.getByRole("checkbox", { name: /^Martin Král/ }));

    expect(
      screen.getByRole("heading", { name: "12 of 16 picked" }),
    ).toBeInTheDocument();
    expect(screen.getByText("12 players make 6 pairs")).toBeInTheDocument();
    expect(
      screen.getByText("The round robin will have 15 matches in 5 rounds."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next: draw pairs" }));
    await waitFor(() => {
      expect(view.state.location.pathname).toBe(
        generatePath(paths.setupDraw, { leagueId, tournamentId: id }),
      );
    });
    expect((await setupOf(id)).player_ids).toHaveLength(12);
  });

  it("explains an odd number and filters the list without accents", async () => {
    const user = userEvent.setup();
    const id = await createDraft();
    await pickPlayers(id, 11);
    renderAt(playersPage(id));

    expect(
      await screen.findByText("11 players make 5 pairs"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/one player drawn by lot sits the tournament out/),
    ).toBeInTheDocument();

    await user.type(
      screen.getByRole("searchbox", { name: "Find a player" }),
      "novakova",
    );
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(
      screen.getByRole("checkbox", { name: /Anna Nováková/ }),
    ).toBeChecked();
    await user.clear(screen.getByRole("searchbox"));
    await user.type(screen.getByRole("searchbox"), "zzz");
    expect(screen.getByText("No player matches “zzz”.")).toBeInTheDocument();
  });

  it("keeps Doubles to an even number of players", async () => {
    const id = await createDraft({ type: "doubles" });
    await pickPlayers(id, 5);
    renderAt(playersPage(id));

    expect(
      await screen.findByText("Doubles needs an even number"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Next: make pairs" }),
    ).toBeDisabled();
  });

  it("goes back to the format of the same tournament", async () => {
    const user = userEvent.setup();
    const id = await createDraft();
    await pickPlayers(id, 8);
    const view = renderAt(playersPage(id));

    await user.click(await screen.findByRole("button", { name: "Back" }));

    await waitFor(() => {
      expect(view.state.location.pathname).toBe(
        generatePath(paths.newTournament, { leagueId }),
      );
    });
    expect(view.state.location.search).toBe(`?tournament=${id}`);
  });

  it("shows the Czech plurals for the pairs", async () => {
    await i18n.changeLanguage("cs");
    const id = await createDraft();
    await pickPlayers(id, 4);
    renderAt(playersPage(id));

    expect(
      await screen.findByText("Z 4 hráčů vzniknou 2 dvojice"),
    ).toBeInTheDocument();
  });

  it.each([
    ["phone", 390],
    ["desktop", 1280],
  ])("has no axe violations on a %s", async (_, width) => {
    stubViewport(width);
    const id = await createDraft();
    await pickPlayers(id, 12);
    renderAt(playersPage(id));
    await screen.findByRole("heading", { name: "12 of 16 picked" });

    expect(await axeViolations()).toEqual([]);
  });
});
