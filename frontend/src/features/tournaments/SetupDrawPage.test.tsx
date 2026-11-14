import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { TEST_LEAGUE_ID } from "@/test/fake/ids";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";
import { server } from "@/test/server";
import {
  axeViolations,
  createDraft,
  drawElsewhere,
  markTopPlayersElsewhere,
  nth,
  pickPlayers,
  setupOf,
  tournamentOf,
} from "@/test/setupTestHelpers";

const leagueId = TEST_LEAGUE_ID;
const drawPage = (tournamentId: string) =>
  generatePath(paths.setupDraw, { leagueId, tournamentId });

async function dypWith(count: number) {
  const id = await createDraft();
  await pickPlayers(id, count);
  return id;
}

describe("setup: draw the pairs (screen 4)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("shows the halves, the drawn pairs and the seeds of a DYP, and draws again", async () => {
    const user = userEvent.setup();
    const id = await dypWith(12);
    const before = await setupOf(id);
    renderAt(drawPage(id));

    expect(
      await screen.findByRole("heading", { name: "Top half" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Bottom half" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Drawn pairs" }),
    ).toBeInTheDocument();
    const seeds = screen.getByRole("list", { name: "Seed order" });
    expect(within(seeds).getAllByRole("listitem")).toHaveLength(6);

    await user.click(screen.getByRole("button", { name: "Draw again" }));

    await waitFor(async () => {
      expect((await setupOf(id)).draw_counter).toBe(before.draw_counter + 1);
    });
  });

  it("tells the organizer when another device changed the draw, then draws on the new counter", async () => {
    const user = userEvent.setup();
    const id = await dypWith(12);
    renderAt(drawPage(id));
    await user.click(
      await screen.findByRole("radio", { name: "Random shuffle" }),
    );
    const shuffle = await screen.findByRole("button", {
      name: "Shuffle again",
    });
    await waitFor(async () => {
      expect((await setupOf(id)).seeding_method).toBe("random");
    });
    // Let the screen load the counter of the random draw before the other device moves it.
    await screen.findByRole("radio", { name: "Random shuffle", checked: true });
    await drawElsewhere(id, "seeds");
    const stale = (await setupOf(id)).draw_counter;

    await user.click(shuffle);

    expect(
      await screen.findByText(/changed on another device/),
    ).toBeInTheDocument();
    expect((await setupOf(id)).draw_counter).toBe(stale);

    await user.click(screen.getByRole("button", { name: "Shuffle again" }));
    await waitFor(async () => {
      expect((await setupOf(id)).draw_counter).toBe(stale + 1);
    });
  });

  it("moves a pair up and down the seeds by hand", async () => {
    const user = userEvent.setup();
    const id = await dypWith(12);
    const first = (await tournamentOf(id)).entries[0];
    renderAt(drawPage(id));

    const items = await screen.findAllByRole("button", {
      name: /^Move .* down one seed$/,
    });
    await user.click(nth(items, 0));

    await waitFor(async () => {
      const entries = (await tournamentOf(id)).entries;
      expect(entries.find((entry) => entry.id === first?.id)?.seed).toBe(2);
    });
    expect(
      screen.getAllByRole("button", { name: /^Move .* up one seed$/ })[0],
    ).toBeDisabled();
  });

  it("asks for complete, equal halves when they are set by hand", async () => {
    const user = userEvent.setup();
    const id = await dypWith(12);
    renderAt(drawPage(id));
    await user.click(await screen.findByRole("radio", { name: "By hand" }));
    const rows = await screen.findAllByRole("radiogroup", { name: /^1\. / });
    await user.click(
      within(nth(rows, 0)).getByRole("radio", { name: "Bottom" }),
    );

    expect(await screen.findByText("Halves not ready")).toBeInTheDocument();
    expect(screen.getByText(/Top half: 5, bottom half: 7/)).toBeInTheDocument();
    expect(screen.getByText("Next: review")).toBeDisabled();

    await user.click(
      within(
        await screen.findByRole("radiogroup", { name: /^7\. / }),
      ).getByRole("radio", {
        name: "Top",
      }),
    );
    await waitFor(() => {
      expect(screen.queryByText("Halves not ready")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Next: review" })).toBeEnabled();
  });

  it("leaves one player out of an odd DYP and says who", async () => {
    const id = await dypWith(13);
    const left = (await setupOf(id)).halves.find((h) => h.half === "left_out");
    renderAt(drawPage(id));

    expect(
      await screen.findByText("One player is left out"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not play in this tournament/),
    ).toBeInTheDocument();
    expect(left).toBeDefined();
  });

  it("makes the pairs of a Doubles by hand", async () => {
    const user = userEvent.setup();
    const id = await createDraft({ type: "doubles" });
    await pickPlayers(id, 4);
    renderAt(drawPage(id));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Make the pairs" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Not everyone has a partner")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Make a pair" })).toBeDisabled();
    const alone = screen.getByRole("toolbar", {
      name: "Players without a partner",
    });
    const players = within(alone).getAllByRole("button");
    await user.click(nth(players, 0));
    await user.click(nth(players, 1));
    await user.click(screen.getByRole("button", { name: "Make a pair" }));

    await waitFor(async () => {
      expect((await tournamentOf(id)).entries).toHaveLength(1);
    });
    await user.click(
      screen.getByRole("button", { name: "Pair the rest at random" }),
    );
    await waitFor(async () => {
      expect((await tournamentOf(id)).entries).toHaveLength(2);
    });
    expect(
      await screen.findByText("Everyone has a partner"),
    ).toBeInTheDocument();
    await user.click(
      nth(screen.getAllByRole("button", { name: /^Break up / }), 0),
    );
    await waitFor(async () => {
      expect((await tournamentOf(id)).entries).toHaveLength(1);
    });
  });

  it("only seeds Singles, and lets the organizer mark the top players of a Monster DYP", async () => {
    const singles = await createDraft({ type: "singles" });
    await pickPlayers(singles, 5);
    const view = renderAt(drawPage(singles));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Set the seeding" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Top half" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Setup steps" }),
    ).toHaveTextContent("Seeding");
    expect(view.state.location.pathname).toBe(drawPage(singles));
  });

  it("lets the organizer mark the top players of a Monster DYP", async () => {
    const user = userEvent.setup();
    const id = await createDraft({
      type: "monster_dyp",
      group_phase: "monster_dyp",
    });
    await pickPlayers(id, 9);
    renderAt(drawPage(id));

    expect(
      await screen.findByRole("heading", { name: "Top players (up to 2)" }),
    ).toBeInTheDocument();
    const boxes = screen.getAllByRole("checkbox");
    await user.click(nth(boxes, 3));
    await waitFor(async () => {
      expect((await setupOf(id)).top_player_ids).toHaveLength(1);
    });
    await user.click(nth(boxes, 4));
    await waitFor(() => {
      expect(boxes[5]).toBeDisabled();
    });
  });

  it("FR-041: with the marks used up, only the marked players keep an enabled checkbox", async () => {
    const user = userEvent.setup();
    const id = await createDraft({
      type: "monster_dyp",
      group_phase: "monster_dyp",
    });
    await pickPlayers(id, 9);
    renderAt(drawPage(id));
    await screen.findByRole("heading", { name: "Top players (up to 2)" });

    const boxes = screen.getAllByRole("checkbox");
    await user.click(nth(boxes, 0));
    await user.click(nth(boxes, 1));

    await waitFor(() => {
      expect(boxes.map((box) => box.hasAttribute("disabled"))).toEqual([
        false,
        false,
        ...Array<boolean>(7).fill(true),
      ]);
    });
  });

  it("FR-041: shows a 422 too_many_top_players in an alert with the limit", async () => {
    server.use(
      http.put(
        "*/api/v1/leagues/:leagueId/tournaments/:tournamentId/setup/top-players",
        () =>
          HttpResponse.json(
            { code: "too_many_top_players", detail: { max: 2 } },
            { status: 422 },
          ),
      ),
    );
    const user = userEvent.setup();
    const id = await createDraft({
      type: "monster_dyp",
      group_phase: "monster_dyp",
    });
    await pickPlayers(id, 9);
    renderAt(drawPage(id));
    await screen.findByRole("heading", { name: "Top players (up to 2)" });

    await user.click(nth(screen.getAllByRole("checkbox"), 0));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many top players: at most 2",
    );
  });

  it("ADR-008: reloads the section on a 409, so it shows the marks set elsewhere", async () => {
    const user = userEvent.setup();
    const id = await createDraft({
      type: "monster_dyp",
      group_phase: "monster_dyp",
    });
    const picked = await pickPlayers(id, 9);
    renderAt(drawPage(id));
    await screen.findByRole("heading", { name: "Top players (up to 2)" });
    const boxes = screen.getAllByRole("checkbox");

    // Another device started the tournament while this screen still shows setup.
    await markTopPlayersElsewhere(id, [nth(picked.player_ids, 8)]);
    server.use(
      http.put(
        "*/api/v1/leagues/:leagueId/tournaments/:tournamentId/setup/top-players",
        () =>
          HttpResponse.json(
            { code: "tournament_not_in_setup", detail: {} },
            { status: 409 },
          ),
        { once: true },
      ),
    );
    await user.click(nth(boxes, 0));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This changed on another device",
    );
    await waitFor(() => {
      expect(nth(screen.getAllByRole("checkbox"), 8)).toBeChecked();
    });
    expect(nth(screen.getAllByRole("checkbox"), 0)).not.toBeChecked();
  });

  it.each([
    ["DYP on a phone", 390, "dyp"],
    ["DYP on a desktop", 1280, "dyp"],
    ["Doubles", 390, "doubles"],
  ] as const)("has no axe violations: %s", async (_, width, type) => {
    stubViewport(width);
    const id = await createDraft({ type });
    await pickPlayers(id, 12);
    renderAt(drawPage(id));
    await screen.findByRole("heading", { name: "Seeding" });

    expect(await axeViolations()).toEqual([]);
  });
});
