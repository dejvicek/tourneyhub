import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { DEMO_LEAGUE_ID, DEMO_SHARE_TOKEN } from "@/demo/seed";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { stubViewport } from "@/test/media";
import { renderAt } from "@/test/renderApp";

const tournaments = generatePath(paths.tournaments, {
  leagueId: DEMO_LEAGUE_ID,
});

describe("LeagueShell", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("on a phone, shows the league and season and a bottom bar of four sections", async () => {
    const user = userEvent.setup();
    renderAt(tournaments);

    const nav = await screen.findByRole("navigation", { name: "Main" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      "Tournaments",
      "Standings",
      "Players",
      "League",
    ]);
    expect(
      within(nav).getByRole("link", { name: "Tournaments" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      await screen.findByRole("link", {
        name: "Thursday Foosball, Season 1",
      }),
    ).toHaveAttribute("href", paths.myLeagues);
    expect(
      screen.queryByRole("button", { name: "Copy share link" }),
    ).not.toBeInTheDocument();

    await user.click(within(nav).getByRole("link", { name: "Standings" }));

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Season standings",
      }),
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "Standings" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("on a tablet, shows the sections as tabs under the header", async () => {
    stubViewport(768);
    renderAt(tournaments);

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(
      within(screen.getByRole("banner")).getByRole("navigation", {
        name: "Main",
      }),
    ).toBe(nav);
    expect(within(nav).getAllByRole("link")).toHaveLength(4);
  });

  it("on a desktop, shows the sidebar with the switcher, share link and user", async () => {
    stubViewport(1280);
    const user = userEvent.setup();
    renderAt(tournaments);

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual([
      "Tournaments",
      "Season standings",
      "Players",
      "League settings",
    ]);
    expect(
      await screen.findByRole("link", { name: /Switch league/ }),
    ).toHaveAttribute("href", paths.myLeagues);
    expect(
      await screen.findByText("Signed in as Alex Organizer"),
    ).toBeInTheDocument();

    await user.click(
      within(nav).getByRole("link", { name: "League settings" }),
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: "League settings" }),
    ).toBeInTheDocument();

    const copy = screen.getByRole("button", { name: "Copy share link" });
    await waitFor(() => {
      expect(copy).toBeEnabled();
    });
    await user.click(copy);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Share link copied",
    );
    expect(await navigator.clipboard.readText()).toBe(
      `${location.origin}/public/${DEMO_SHARE_TOKEN}`,
    );
  });

  it("shows the league's screens in Czech", async () => {
    await i18n.changeLanguage("cs");
    renderAt(tournaments);

    const nav = await screen.findByRole("navigation", {
      name: "Hlavní",
    });
    expect(within(nav).getByRole("link", { name: "Turnaje" })).toBeVisible();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Turnaje sezóny" }),
    ).toBeInTheDocument();
  });
});
