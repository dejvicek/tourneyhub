import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { DEMO_LEAGUE_ID } from "@/demo/ids";
import { db } from "@/demo/store";
import { axeViolations } from "@/features/auth/axeCheck";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { renderAt } from "@/test/renderApp";

const players = generatePath(paths.players, { leagueId: DEMO_LEAGUE_ID });

function status() {
  return screen.getByRole("status");
}

describe("PlayersPage", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("FR-012: lists the league's players with their count", async () => {
    renderAt(players);

    expect(
      // The first test of the file also loads the lazy area.
      await screen.findByRole(
        "heading",
        { name: "16 players" },
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
  });

  it("BR-001: a rename to another player's name, in other letter case, is refused", async () => {
    const user = userEvent.setup();
    renderAt(players);

    await user.click(
      await screen.findByRole("button", { name: "Rename Anna Nováková" }),
    );
    const field = screen.getByLabelText("New name for Anna Nováková");
    await user.clear(field);
    await user.type(field, "petr SVOBODA");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(field).toHaveAttribute("aria-invalid", "true");
    });
    expect(field).toHaveAccessibleDescription(
      "Petr Svoboda is already on the list.",
    );
    expect(db().players.find((p) => p.name === "Anna Nováková")).toBeDefined();
  });

  it("FR-012: renames a player", async () => {
    const user = userEvent.setup();
    renderAt(players);

    await user.click(
      await screen.findByRole("button", { name: "Rename Anna Nováková" }),
    );
    const field = screen.getByLabelText("New name for Anna Nováková");
    await user.clear(field);
    await user.type(field, "Anna Nová");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(status()).toHaveTextContent("Renamed to Anna Nová.");
    });
  });

  it("BR-001: adding a taken name says so", async () => {
    const user = userEvent.setup();
    renderAt(players);

    const name = await screen.findByLabelText("Name");
    await user.type(name, "JANA dvořáková");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(name).toHaveAccessibleDescription(
        "Jana Dvořáková is already on the list.",
      );
    });
  });

  it("FR-012, BR-002: removes a player after the confirmation and restores them", async () => {
    const user = userEvent.setup();
    renderAt(players);

    await user.click(
      await screen.findByRole("button", { name: "Remove Filip Šimek" }),
    );
    const confirm = await screen.findByRole("alertdialog", {
      name: "Remove Filip Šimek?",
    });
    await user.click(within(confirm).getByRole("button", { name: "Remove" }));

    await waitFor(() => {
      expect(status()).toHaveTextContent("Filip Šimek is removed.");
    });
    const removed = await screen.findByRole("region", {
      name: "Removed player (1)",
    });
    expect(
      await screen.findByRole("heading", { name: "15 players" }),
    ).toBeInTheDocument();

    await user.click(
      within(removed).getByRole("button", { name: "Restore Filip Šimek" }),
    );

    await waitFor(() => {
      expect(status()).toHaveTextContent("Filip Šimek is back on the list.");
    });
    expect(
      await screen.findByRole("heading", { name: "16 players" }),
    ).toBeInTheDocument();
  });

  it("BR-002: a player in an unfinished tournament cannot be removed", async () => {
    const user = userEvent.setup();
    renderAt(players);

    await user.click(
      await screen.findByRole("button", { name: "Remove Anna Nováková" }),
    );
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Remove" }));

    expect(
      await screen.findByText(
        "Anna Nováková plays in a tournament that is not finished, so they cannot be removed yet.",
      ),
    ).toBeInTheDocument();
  });

  it("BR-001: a removed player's name is refused with an offer to restore them", async () => {
    const filip = db().players.find((p) => p.name === "Filip Šimek");
    if (filip === undefined) {
      throw new Error("The seed has Filip Šimek");
    }
    filip.removed_at = "2026-10-01T18:00:00Z";
    const user = userEvent.setup();
    renderAt(players);

    const name = await screen.findByLabelText("Name");
    await user.type(name, "filip šimek");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(name).toHaveAccessibleDescription(
        "Filip Šimek is a removed player. Restore them instead.",
      );
    });
    await user.click(
      within(screen.getByRole("form", { name: "Add a player" })).getByRole(
        "button",
        { name: "Restore Filip Šimek" },
      ),
    );

    await waitFor(() => {
      expect(status()).toHaveTextContent("Filip Šimek is back on the list.");
    });
    expect(filip.removed_at).toBeNull();
  });

  it("a league full at 500 players says so at the field", async () => {
    const count = db().players.filter(
      (p) => p.league_id === DEMO_LEAGUE_ID,
    ).length;
    for (let i = count; i < 500; i++) {
      db().players.push({
        id: crypto.randomUUID(),
        league_id: DEMO_LEAGUE_ID,
        name: `Removed ${String(i)}`,
        removed_at: "2026-10-01T18:00:00Z",
      });
    }
    const user = userEvent.setup();
    renderAt(players);

    const name = await screen.findByLabelText("Name");
    await user.type(name, "One Too Many");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(name).toHaveAccessibleDescription(
        "A league holds at most 500 players, removed ones included.",
      );
    });
  });

  it("a name with an invisible character is refused at the field", async () => {
    const user = userEvent.setup();
    renderAt(players);

    const name = await screen.findByLabelText("Name");
    await user.type(name, "Zero\u200bWidth");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(name).toHaveAccessibleDescription(
        "Use visible letters only, without hidden or line-break characters.",
      );
    });
  });

  it("has no axe violations", async () => {
    renderAt(players);
    await screen.findByRole("heading", { name: "16 players" });

    expect(await axeViolations()).toEqual([]);
  });
});
