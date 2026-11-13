import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { TEST_LEAGUE_ID } from "@/test/fake/ids";
import { createSeed } from "@/test/fake/seed";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";

const running = createSeed().tournaments.find((t) => t.state === "in_progress");
const params = {
  leagueId: TEST_LEAGUE_ID,
  tournamentId: running?.id ?? "",
  matchId: running?.rounds.at(-1)?.matches.at(-1)?.id ?? "",
};
const moveMatch = generatePath(paths.moveMatch, params);
const fields = generatePath(paths.fields, params);

// The overlays are nested routes; the moving of a match (6c) stands for all.
describe("ResponsiveSheet", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("on a phone, is a modal bottom sheet that closes to its parent", async () => {
    const user = userEvent.setup();
    const view = renderAt(moveMatch);

    const sheet = await screen.findByRole("dialog", {
      // The match waits, so the overlay puts it on a field (G2's 6c).
      name: "Put this match on a field",
    });
    await waitFor(
      () => {
        expect(sheet).toHaveAccessibleDescription(/in line\.$/);
      },
      { timeout: 3000 },
    );
    // Modal: the screen behind it is hidden from assistive technology.
    expect(
      screen.queryByRole("heading", {
        level: 1,
        name: "Fields: now playing and waiting",
      }),
    ).not.toBeInTheDocument();

    await user.click(within(sheet).getByRole("button", { name: "Close" }));

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Fields: now playing and waiting",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(view.state.location.pathname).toBe(fields);
  });

  it("on a tablet, is a centred dialog that Escape closes", async () => {
    stubViewport(768);
    const user = userEvent.setup();
    const view = renderAt(moveMatch);

    await screen.findByRole("dialog", { name: "Put this match on a field" });
    await user.keyboard("{Escape}");

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Fields: now playing and waiting",
      }),
    ).toBeInTheDocument();
    expect(view.state.location.pathname).toBe(fields);
  });

  it("on a desktop, is a side panel beside a screen that stays usable", async () => {
    stubViewport(1280);
    const user = userEvent.setup();
    const view = renderAt(moveMatch);

    await screen.findByRole("dialog", { name: "Put this match on a field" });
    const parent = screen.getByRole("heading", {
      level: 1,
      name: "Fields: now playing and waiting",
    });
    await user.click(parent);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(view.state.location.pathname).toBe(moveMatch);
  });
});
