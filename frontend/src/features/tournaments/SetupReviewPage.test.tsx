import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { DEMO_LEAGUE_ID } from "@/demo/ids";
import {
  axeViolations,
  createDraft,
  drawElsewhere,
  pickPlayers,
  startTournament,
  tournamentOf,
} from "@/demo/setupTestHelpers";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";

const leagueId = DEMO_LEAGUE_ID;
const reviewPage = (tournamentId: string) =>
  generatePath(paths.setupReview, { leagueId, tournamentId });

async function dypWith(count: number, format = {}) {
  const id = await createDraft(format);
  await pickPlayers(id, count);
  return id;
}

function row(label: string) {
  const term = screen.getByText(label, { selector: "dt" });
  return term.nextElementSibling;
}

describe("setup: review and start (screen 5)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("summarises the choices and the first round, then generates and starts", async () => {
    const user = userEvent.setup();
    const id = await dypWith(12, { name: "DYP on 22 October" });
    const view = renderAt(reviewPage(id));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Ready to start?" }),
    ).toBeInTheDocument();
    await screen.findAllByText("VS");
    expect(row("Name")).toHaveTextContent("DYP on 22 October");
    expect(row("Type")).toHaveTextContent("DYP");
    expect(row("Pairs")).toHaveTextContent("6 pairs, drawn from 12 players");
    expect(row("Group phase")).toHaveTextContent("Round robin, once");
    expect(row("Matches")).toHaveTextContent("15 in 5 rounds, all BO1");
    expect(row("Final")).toHaveTextContent("Same as knockout");
    expect(row("Draws")).toHaveTextContent("Not allowed in this league");
    // BR-071: a round robin has no points for sitting out.
    expect(
      screen.queryByText("Sit-out points", { selector: "dt" }),
    ).not.toBeInTheDocument();
    expect(row("Knockout")).toHaveTextContent("Decide after the group phase");
    expect(screen.getAllByText("VS")).toHaveLength(3);
    expect(screen.getByText("Rounds 2 to 5 follow.")).toBeInTheDocument();
    expect(screen.getByText("Nobody sits out.")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Generate and start" }),
    );

    await waitFor(() => {
      expect(view.state.location.pathname).toBe(
        generatePath(paths.schedule, { leagueId, tournamentId: id }),
      );
    });
    const started = await tournamentOf(id);
    expect(started.state).toBe("in_progress");
    expect(started.rounds).toHaveLength(5);
  });

  it("does not start on a draw that changed on another device", async () => {
    const user = userEvent.setup();
    const id = await dypWith(12);
    renderAt(reviewPage(id));
    const start = await screen.findByRole("button", {
      name: "Generate and start",
    });
    await screen.findByRole("heading", { name: "First round" });
    await drawElsewhere(id, "pairs");

    await user.click(start);

    expect(
      await screen.findByText(/changed on another device/),
    ).toBeInTheDocument();
    expect((await tournamentOf(id)).state).toBe("setup");
  });

  it.each([
    [
      "too few entries",
      { type: "singles" as const },
      1,
      "Not enough entries: at least 2 are needed.",
    ],
    [
      "a player without a partner",
      { type: "doubles" as const },
      3,
      "3 players have no partner yet.",
    ],
  ])(
    "names the reason and does not offer the start with %s",
    async (_, format, count, reason) => {
      const id = await dypWith(count, format);
      renderAt(reviewPage(id));

      expect(await screen.findByText(reason)).toHaveAttribute("role", "status");
      expect(row("Matches")).toHaveTextContent("Not available yet");
      expect(
        screen.getByRole("button", { name: "Generate and start" }),
      ).toBeDisabled();
      expect(screen.queryByText("VS")).not.toBeInTheDocument();
    },
  );

  it("keeps the start disabled while the schedule loads, then enables it", async () => {
    const id = await dypWith(12);
    renderAt(reviewPage(id));

    expect(
      await screen.findByRole("button", { name: "Generate and start" }),
    ).toBeDisabled();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Generate and start" }),
      ).toBeEnabled();
    });
    expect(screen.queryByText(/have no partner|Not enough/)).toBeNull();
  });

  it("shows the whole schedule on a tablet, and the open rounds of a Swiss", async () => {
    stubViewport(768);
    const id = await dypWith(12);
    renderAt(reviewPage(id));

    expect(
      await screen.findByRole("heading", { name: "Schedule" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Round 5" }),
    ).toBeInTheDocument();
    const swiss = await dypWith(11, { group_phase: "swiss" });
    renderAt(reviewPage(swiss));
    expect(
      await screen.findAllByText(
        "You add the next rounds yourself, one at a time.",
      ),
    ).not.toHaveLength(0);
  });

  it("goes on to the tournament when setup is already closed (D21)", async () => {
    const id = await dypWith(12);
    await startTournament(id);
    const view = renderAt(reviewPage(id));

    await waitFor(() => {
      expect(view.state.location.pathname).toBe(
        generatePath(paths.schedule, { leagueId, tournamentId: id }),
      );
    });
    expect(
      screen.queryByRole("button", { name: "Generate and start" }),
    ).not.toBeInTheDocument();
  });

  it("shows its texts in Czech", async () => {
    await i18n.changeLanguage("cs");
    const id = await dypWith(12);
    renderAt(reviewPage(id));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Můžeme začít?" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("15 v 5 kolech, vše BO1"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Vytvořit rozpis a začít" }),
    ).toBeInTheDocument();
  });

  it.each([
    ["phone", 390],
    ["desktop", 1280],
  ])("has no axe violations on a %s", async (_, width) => {
    stubViewport(width);
    const id = await dypWith(12);
    renderAt(reviewPage(id));
    await screen
      .findByText("VS", { selector: "span", exact: false })
      .catch(() => undefined);
    await screen.findAllByText("VS");

    expect(await axeViolations()).toEqual([]);
    expect(
      within(
        screen.getByRole("navigation", { name: "Setup steps" }),
      ).getAllByRole("listitem"),
    ).toHaveLength(4);
  });
});
