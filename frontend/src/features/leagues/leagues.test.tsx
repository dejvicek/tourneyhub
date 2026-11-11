import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { syncBracket } from "@/demo/finalsEngine";
import { DEMO_LEAGUE_ID } from "@/demo/ids";
import { activeSeason, db } from "@/demo/store";
import { axeViolations } from "@/features/auth/axeCheck";
import { i18n } from "@/i18n";
import { newId } from "@/lib/newId";
import { paths } from "@/lib/paths";
import { renderAt } from "@/test/renderApp";

const settings = generatePath(paths.leagueSettings, {
  leagueId: DEMO_LEAGUE_ID,
});

/**
 * BR-010 allows a new season only when every tournament is finished. A
 * bracket with matches still to play reopens itself (FR-037), so the
 * tournaments that stay unfinished are deleted, which BR-010 allows too.
 */
function finishEveryTournament() {
  for (const tournament of db().tournaments) {
    tournament.state = "finished";
    syncBracket(tournament);
  }
  const state = db();
  state.tournaments = state.tournaments.filter((t) => t.state === "finished");
}

describe("leagues", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("FR-007: lists the organizer's leagues with their season", async () => {
    renderAt(paths.myLeagues);

    const card = await screen.findByRole("link", {
      name: "Open Thursday Foosball",
    });
    expect(card).toHaveAttribute(
      "href",
      generatePath(paths.tournaments, { leagueId: DEMO_LEAGUE_ID }),
    );
    expect(await within(card).findByText("Season 1")).toBeInTheDocument();
  });

  it("FR-010: creates a league with Season 1 and opens it", async () => {
    const user = userEvent.setup();
    const view = renderAt(paths.myLeagues);

    await user.click(await screen.findByRole("button", { name: "New league" }));
    const dialog = await screen.findByRole("dialog", { name: "New league" });
    await user.type(within(dialog).getByLabelText("League name"), "Pub Cup");
    await user.click(
      within(dialog).getByRole("button", { name: "Create the league" }),
    );

    await waitFor(() => {
      expect(view.state.location.pathname).toMatch(
        /^\/leagues\/[0-9a-f-]{36}\/tournaments$/,
      );
    });
    const created = db().leagues.find((row) => row.name === "Pub Cup");
    expect(created?.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7/);
    expect(activeSeason(created?.id ?? "")?.number).toBe(1);
  });

  it("FR-010: an empty name is shown at the field", async () => {
    const user = userEvent.setup();
    renderAt(paths.myLeagues);

    await user.click(await screen.findByRole("button", { name: "New league" }));
    const dialog = await screen.findByRole("dialog", { name: "New league" });
    await user.click(
      within(dialog).getByRole("button", { name: "Create the league" }),
    );

    const name = within(dialog).getByLabelText("League name");
    await waitFor(() => {
      expect(name).toHaveAttribute("aria-invalid", "true");
    });
    expect(name).toHaveAccessibleDescription("Enter a name.");
  });

  it("FR-011: an increasing points table is refused at its place", async () => {
    const user = userEvent.setup();
    renderAt(settings);

    const third = await screen.findByLabelText("Points for place 3");
    await user.clear(third);
    await user.type(third, "9");
    await user.click(screen.getByRole("button", { name: "Save points" }));

    await waitFor(() => {
      expect(third).toHaveAttribute("aria-invalid", "true");
    });
    expect(third).toHaveAccessibleDescription(
      "Place 3 is worth more than the place above it.",
    );
    expect(activeSeason(DEMO_LEAGUE_ID)?.placement_points).toEqual([
      10, 8, 6, 4, 2,
    ]);
  });

  it("FR-011, BR-012: saves a longer table", async () => {
    const user = userEvent.setup();
    renderAt(settings);

    await user.click(
      await screen.findByRole("button", { name: "Add a place" }),
    );
    await user.click(screen.getByRole("button", { name: "Save points" }));

    await waitFor(() => {
      expect(activeSeason(DEMO_LEAGUE_ID)?.placement_points).toEqual([
        10, 8, 6, 4, 2, 0,
      ]);
    });
  });

  it("FR-011: saves the league's name, draws and defaults", async () => {
    const user = userEvent.setup();
    renderAt(settings);

    const name = await screen.findByLabelText("League name");
    await user.clear(name);
    await user.type(name, "Thursday Kicker");
    await user.click(screen.getByRole("switch", { name: /Draws allowed/ }));
    await user.click(screen.getByRole("button", { name: "More: Fields" }));
    await user.click(screen.getByRole("radio", { name: /BO3/ }));
    await user.click(
      screen.getByRole("button", { name: "Save league settings" }),
    );

    await waitFor(() => {
      expect(
        db().leagues.find((row) => row.id === DEMO_LEAGUE_ID),
      ).toMatchObject({
        name: "Thursday Kicker",
        draws_allowed: true,
        default_field_count: 3,
        default_match_format: "bo3",
      });
    });
  });

  it("BR-010: a running tournament keeps the next season shut and says which", async () => {
    renderAt(settings);

    expect(
      await screen.findByText(
        /Finish or delete these tournaments first: .*Thursday DYP/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start Season 2" }),
    ).toBeDisabled();
  });

  it("FR-021, ADR-008: a season started elsewhere meanwhile is a conflict that reloads", async () => {
    finishEveryTournament();
    const user = userEvent.setup();
    renderAt(settings);
    const start = await screen.findByRole("button", { name: "Start Season 2" });
    await waitFor(() => {
      expect(start).toBeEnabled();
    });

    // Another device starts Season 2 while this screen still shows Season 1.
    const first = activeSeason(DEMO_LEAGUE_ID);
    if (first === undefined) {
      throw new Error("The seed has an active season");
    }
    first.state = "closed";
    first.closed_at = new Date().toISOString();
    db().seasons.push({
      ...first,
      id: newId(),
      number: 2,
      state: "active",
      closed_at: null,
    });

    await user.click(start);
    await user.click(
      await screen.findByRole("button", { name: "Close Season 1 and start" }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(/Season 2 was started on another device/),
      ).toBeInTheDocument();
    });
    expect(
      await screen.findByRole("button", { name: "Start Season 3" }),
    ).toBeInTheDocument();
    expect(db().seasons.filter((s) => s.number === 3)).toHaveLength(0);
  });

  it("FR-021, FR-022: starts the next season; the closed one is read-only", async () => {
    finishEveryTournament();
    const user = userEvent.setup();
    renderAt(settings);
    const start = await screen.findByRole("button", { name: "Start Season 2" });
    await waitFor(() => {
      expect(start).toBeEnabled();
    });

    await user.click(start);
    await user.click(
      await screen.findByRole("button", { name: "Close Season 1 and start" }),
    );

    expect(await screen.findByText("Season 2 started.")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Closed seasons are read-only. Only their name can change.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Rename Season 1" }),
    ).toBeInTheDocument();
  });

  it("FR-013: deletes the league after the confirmation", async () => {
    const user = userEvent.setup();
    const view = renderAt(settings);

    await user.click(
      await screen.findByRole("button", { name: "Delete the league" }),
    );
    const confirm = await screen.findByRole("alertdialog", {
      name: "Delete Thursday Foosball?",
    });
    await user.click(
      within(confirm).getByRole("button", { name: "Delete for good" }),
    );

    await waitFor(() => {
      expect(view.state.location.pathname).toBe(paths.myLeagues);
    });
    expect(
      await screen.findByText("You have no leagues yet."),
    ).toBeInTheDocument();
    expect(
      db().seasons.filter((season) => season.league_id === DEMO_LEAGUE_ID),
    ).toHaveLength(0);
  });

  it.each([
    ["my leagues", paths.myLeagues, "My leagues"],
    ["league settings", settings, "League settings"],
  ])("the %s screen has no axe violations", async (_, path, title) => {
    renderAt(path);
    await screen.findByRole("heading", { level: 1, name: title });
    await screen.findAllByRole("button");

    expect(await axeViolations()).toEqual([]);
  });

  it("D34: fields stop at 32 and goals at 99, as the API's limits say", async () => {
    const user = userEvent.setup();
    renderAt(settings);

    const fields = await screen.findByLabelText("Fields");
    await user.clear(fields);
    await user.type(fields, "33");
    await user.click(
      screen.getByRole("button", { name: "Save league settings" }),
    );

    expect(fields).toHaveAccessibleDescription(/Use 32 or fewer\./);
    expect(
      db().leagues.find((row) => row.id === DEMO_LEAGUE_ID)
        ?.default_field_count,
    ).toBe(2);

    await user.clear(fields);
    await user.type(fields, "32");
    expect(screen.getByRole("button", { name: "More: Fields" })).toBeDisabled();

    const goals = screen.getByLabelText("Goals per game");
    await user.clear(goals);
    await user.type(goals, "99");
    expect(
      screen.getByRole("button", { name: "More: Goals per game" }),
    ).toBeDisabled();
  });

  it("D34: the points table stops at 256 places", async () => {
    const season = activeSeason(DEMO_LEAGUE_ID);
    if (season === undefined) {
      throw new Error("The league has an active season");
    }
    season.placement_points = Array.from({ length: 256 }, () => 0);
    renderAt(settings);

    expect(
      await screen.findByRole("button", { name: "Add a place" }),
    ).toBeDisabled();
  });

  it("D11: a saved message goes when the next save fails", async () => {
    const user = userEvent.setup();
    renderAt(settings);

    await user.click(
      await screen.findByRole("button", { name: "Save league settings" }),
    );
    expect(
      await screen.findByText("League settings saved."),
    ).toBeInTheDocument();

    const third = screen.getByLabelText("Points for place 3");
    await user.clear(third);
    await user.type(third, "9");
    await user.click(screen.getByRole("button", { name: "Save points" }));

    await waitFor(() => {
      expect(third).toHaveAttribute("aria-invalid", "true");
    });
    expect(
      screen.queryByText("League settings saved."),
    ).not.toBeInTheDocument();
  });
});
