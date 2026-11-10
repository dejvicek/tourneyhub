import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { DEMO_LEAGUE_ID } from "@/demo/ids";
import { route } from "@/demo/route";
import {
  axeViolations,
  createDraft,
  pickPlayers,
  setupOf,
  startTournament,
} from "@/demo/setupTestHelpers";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";
import { server } from "@/test/server";

const leagueId = DEMO_LEAGUE_ID;
const list = generatePath(paths.tournaments, { leagueId });

async function startDraft() {
  const id = await createDraft({ name: "Friday DYP" });
  await pickPlayers(id, 12);
  await startTournament(id);
  return id;
}

describe("the tournament list (screen 1)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("groups the season's tournaments and opens a new one", async () => {
    const user = userEvent.setup();
    await pickPlayers(await createDraft({ name: "Friday DYP" }), 12);
    const view = renderAt(list);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Tournaments" }),
    ).toBeInTheDocument();
    const running = await screen.findByRole("region", { name: "Running now" });
    const finished = screen.getByRole("region", { name: "Finished" });
    expect(
      within(running)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual([
      expect.stringContaining("Thursday DYP"),
      expect.stringContaining("Next Thursday DYP"),
      expect.stringContaining("Friday DYP"),
    ]);
    expect(within(finished).getAllByRole("link")).toHaveLength(2);
    // The running one shows its round and how many matches were played.
    expect(
      await within(running).findByText(
        /Round robin, round 3 of 5\. 7 of 15 matches played\./,
      ),
    ).toBeInTheDocument();
    expect(
      within(running).getByRole("progressbar", {
        name: "Matches played in Thursday DYP",
      }),
    ).toHaveAttribute("aria-valuenow", "7");
    expect(
      await within(running).findByText(/14 players picked\. Not started yet\./),
    ).toBeInTheDocument();
    expect(
      await within(running).findByText(/12 players picked\. Not started yet\./),
    ).toBeInTheDocument();
    expect(await within(finished).findAllByText(/Won by /)).toHaveLength(2);

    await user.click(screen.getByRole("link", { name: "New tournament" }));
    await waitFor(() => {
      expect(view.state.location.pathname).toBe(
        generatePath(paths.newTournament, { leagueId }),
      );
    });
  });

  it("deletes a tournament only after the confirmation", async () => {
    const user = userEvent.setup();
    renderAt(list);

    await user.click(
      await screen.findByRole("button", {
        name: "Actions for October Singles",
      }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: "Delete tournament" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Delete October Singles?",
    });
    await user.click(within(dialog).getByRole("button", { name: "Keep it" }));

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
    expect(
      screen.getByRole("link", { name: /October Singles/ }),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Actions for October Singles" }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: "Delete tournament" }),
    );
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Delete tournament",
      }),
    );

    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: /October Singles/ }),
      ).not.toBeInTheDocument();
    });
    expect(
      screen.getByRole("link", { name: /Autumn Open DYP/ }),
    ).toBeInTheDocument();
  });

  it("goes back to setup from a started tournament without results, but not from one with results", async () => {
    const user = userEvent.setup();
    const id = await startDraft();
    const view = renderAt(list);

    await user.click(
      await screen.findByRole("button", { name: "Actions for Thursday DYP" }),
    );
    expect(
      await screen.findByRole("menuitem", { name: "Delete tournament" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("menuitem", { name: "Back to setup" }),
    ).not.toBeInTheDocument();
    await user.keyboard("{Escape}");

    await user.click(
      await screen.findByRole("button", { name: "Actions for Friday DYP" }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: "Back to setup" }),
    );

    await waitFor(() => {
      expect(view.state.location.pathname).toBe(
        generatePath(paths.setupReview, { leagueId, tournamentId: id }),
      );
    });
    expect((await setupOf(id)).tournament_id).toBe(id);
  });

  it("says so when the season has no tournaments", async () => {
    server.use(
      route(
        "get",
        "/api/v1/leagues/{league_id}/seasons/{season_id}/tournaments",
        () => [],
      ),
    );
    renderAt(list);

    expect(
      await screen.findByText("No tournaments in this season yet."),
    ).toBeInTheDocument();
  });

  it("shows the Czech plural of the players picked", async () => {
    await i18n.changeLanguage("cs");
    await pickPlayers(await createDraft({ name: "Pátek" }), 12);
    await pickPlayers(await createDraft({ name: "Sobota" }), 3);
    await pickPlayers(await createDraft({ name: "Neděle" }), 2);
    renderAt(list);

    expect(
      await screen.findByText(/Vybráno 12 hráčů\. Zatím nezačal\./),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Vybráni 3 hráči\. Zatím nezačal\./),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Vybráni 2 hráči\. Zatím nezačal\./),
    ).toBeInTheDocument();
  });

  it.each([390, 1280])("has no axe violations at %i px", async (width) => {
    stubViewport(width);
    renderAt(list);
    await screen.findAllByText(/Won by /);

    expect(await axeViolations()).toEqual([]);
  });
});
