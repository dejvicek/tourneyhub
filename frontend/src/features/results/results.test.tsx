import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import {
  onField,
  paths,
  playPath,
  runningDyp,
  stubResizeObserver,
} from "@/test/play";
import { renderAt } from "@/test/renderApp";

describe("result entry (screens 7 and 7b)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    stubResizeObserver();
  });

  it("saves a simple result in three taps from the schedule (FR-082)", async () => {
    const user = userEvent.setup();
    const { match } = onField(1);
    renderAt(playPath(paths.tournament));

    // 1: open the match on Field 1.
    const [enter] = await screen.findAllByRole("link", {
      name: /^Enter result,/,
    });
    await user.click(enter ?? document.body);
    const sheet = await screen.findByRole("dialog");
    // 2: the winner's last bead.
    const beads = within(sheet).getAllByRole("radio", {
      name: /^10 goals for/,
    });
    await user.click(beads[1] ?? sheet);
    expect(within(sheet).getByRole("status")).toHaveTextContent(
      /win\. Save now/,
    );
    // 3: save.
    await user.click(
      within(sheet).getByRole("button", { name: "Save result" }),
    );

    await waitFor(() => {
      expect(match.outcome).toBe("side_2");
    });
    expect(match.games).toEqual([
      { game_no: 1, winner: "side_2", score_1: null, score_2: null },
    ]);
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("saves goals for both pairs and says who goes top", async () => {
    const user = userEvent.setup();
    const { match } = onField(2);
    renderAt(playPath(paths.enterResult, { matchId: match.id }));

    const sheet = await screen.findByRole("dialog");
    const [a] = await within(sheet).findAllByRole("textbox");
    await user.type(a ?? sheet, "7");
    await user.click(
      within(sheet).getAllByRole("radio", { name: /^10 goals for/ })[1] ??
        sheet,
    );
    expect(within(sheet).getByRole("status")).toHaveTextContent(/win 10:7/);
    await user.click(
      within(sheet).getByRole("button", { name: "Save result" }),
    );

    await waitFor(() => {
      expect(match.games[0]).toMatchObject({ score_1: 7, score_2: 10 });
    });
  });

  it("rejects a draw in a league without draws (BR-090)", async () => {
    const user = userEvent.setup();
    const { match } = onField(1);
    renderAt(playPath(paths.enterResult, { matchId: match.id }));

    const sheet = await screen.findByRole("dialog");
    for (const bead of await within(sheet).findAllByRole("radio", {
      name: /^8 goals for/,
    })) {
      await user.click(bead);
    }

    expect(within(sheet).getByRole("status")).toHaveTextContent(
      "Draws aren't allowed in this league",
    );
    expect(
      within(sheet).getByRole("button", { name: "Save result" }),
    ).toBeDisabled();
    expect(match.outcome).toBeNull();
  });

  it("records a walkover (FR-052, BR-093)", async () => {
    const user = userEvent.setup();
    const { match } = onField(1);
    renderAt(playPath(paths.enterResult, { matchId: match.id }));

    const sheet = await screen.findByRole("dialog");
    await user.click(
      await within(sheet).findByRole("button", {
        name: "Record a walkover instead",
      }),
    );
    const [first] = within(sheet).getAllByRole("radio");
    await user.click(first ?? sheet);
    await user.click(
      within(sheet).getByRole("button", { name: "Save walkover" }),
    );

    await waitFor(() => {
      expect(match.is_walkover).toBe(true);
    });
    expect(match.outcome).toBe("side_1");
    expect(match.games).toEqual([]);
  });

  it("clears a result after confirming (FR-053, BR-134)", async () => {
    const user = userEvent.setup();
    const played = runningDyp().rounds[0]?.matches[0];
    renderAt(playPath(paths.enterResult, { matchId: played?.id ?? "" }));

    const sheet = await screen.findByRole("dialog");
    await user.click(
      await within(sheet).findByRole("button", { name: "Clear result" }),
    );
    const confirm = await screen.findByRole("alertdialog");
    await user.click(
      within(confirm).getByRole("button", { name: "Clear result" }),
    );

    await waitFor(() => {
      expect(played?.outcome).toBeNull();
    });
    expect(runningDyp().fields.some((f) => f.match_id === played?.id)).toBe(
      false,
    );
  });

  it("enters a best-of-three series, winners only (FR-050, BR-121)", async () => {
    const user = userEvent.setup();
    const t = runningDyp();
    for (const phase of t.phases) {
      phase.match_format = "bo3";
    }
    const { match } = onField(1);
    renderAt(playPath(paths.enterResult, { matchId: match.id }));

    const sheet = await screen.findByRole("dialog");
    await user.click(
      await within(sheet).findByRole("tab", { name: "Winners only" }),
    );
    const game1 = within(sheet).getByRole("radiogroup", {
      name: "Winner of game 1",
    });
    await user.click(within(game1).getAllByRole("radio")[1] ?? game1);
    const game2 = within(sheet).getByRole("radiogroup", {
      name: "Winner of game 2",
    });
    await user.click(within(game2).getAllByRole("radio")[1] ?? game2);

    expect(within(sheet).getByText(/^Not needed:/)).toBeInTheDocument();
    expect(within(sheet).getByRole("status")).toHaveTextContent(
      /win 2:0 in games/,
    );
    await user.click(
      within(sheet).getByRole("button", { name: "Save result" }),
    );

    await waitFor(() => {
      expect(match.outcome).toBe("side_2");
    });
    expect(match.games.map((g) => g.winner)).toEqual(["side_2", "side_2"]);
  });

  it("enters a best-of-three series with goals, game by game", async () => {
    const user = userEvent.setup();
    for (const phase of runningDyp().phases) {
      phase.match_format = "bo3";
    }
    const { match } = onField(1);
    renderAt(playPath(paths.enterResult, { matchId: match.id }));

    const sheet = await screen.findByRole("dialog");
    await within(sheet).findAllByRole("textbox");
    const tenA = () =>
      within(sheet).getAllByRole("radio", { name: /^10 goals for/ })[0] ??
      sheet;
    const goalsB = () => within(sheet).getAllByRole("textbox")[1] ?? sheet;
    await user.click(tenA());
    await user.type(goalsB(), "4");
    expect(
      within(sheet).getByRole("button", { name: /Game 2/ }),
    ).toHaveAttribute("aria-pressed", "true");
    await user.click(tenA());
    await user.type(goalsB(), "6");
    await user.click(
      within(sheet).getByRole("button", { name: "Save result" }),
    );

    await waitFor(() => {
      expect(match.games).toHaveLength(2);
    });
    expect(match.games[1]).toMatchObject({
      winner: "side_1",
      score_1: 10,
      score_2: 6,
    });
  });
});
