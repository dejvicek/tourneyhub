import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { provisionalApi } from "@/api/provisional";
import { DEMO_LEAGUE_ID } from "@/demo/ids";
import { i18n } from "@/i18n";
import { onField, paths, playPath, runningDyp } from "@/test/play";
import { renderAt } from "@/test/renderApp";

/** BR-131: nobody is on two fields at once. */
function playersOnFields(): string[] {
  const t = runningDyp();
  return t.fields.flatMap((field) => {
    const match = t.rounds
      .flatMap((r) => r.matches)
      .find((m) => m.id === field.match_id);
    return match ? match.sides.flatMap((s) => s.player_ids) : [];
  });
}

// The first screen of a file loads its lazy route, slowly under a full run.
configure({ asyncUtilTimeout: 3000 });

describe("fields (screens 6b–6d)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("shows who plays where and why the others wait (6b)", async () => {
    renderAt(playPath(paths.fields));

    expect(await screen.findByText("2 fields, 2 playing")).toBeInTheDocument();
    const waiting = screen.getByRole("region", { name: "Waiting for a field" });
    expect(within(waiting).getAllByRole("listitem").length).toBeGreaterThan(0);
    expect(
      within(waiting).getAllByText(/on Field \d\./).length,
    ).toBeGreaterThan(0);
  });

  it("swaps the matches of two fields without double-booking anyone (FR-093)", async () => {
    const user = userEvent.setup();
    const one = onField(1);
    const two = onField(2);
    renderAt(playPath(paths.moveMatch, { matchId: one.match.id }));

    const sheet = await screen.findByRole("dialog", {
      name: "Move this match",
    });
    await user.click(
      await within(sheet).findByRole("radio", { name: "Field 2" }),
    );
    await user.click(
      within(sheet).getByRole("button", { name: "Swap with Field 2" }),
    );

    await waitFor(() => {
      expect(runningDyp().fields.find((f) => f.number === 2)?.match_id).toBe(
        one.match.id,
      );
    });
    expect(runningDyp().fields.find((f) => f.number === 1)?.match_id).toBe(
      two.match.id,
    );
    const players = playersOnFields();
    expect(new Set(players).size).toBe(players.length);
  });

  it("sends a match back to waiting; its field takes the next match that can be played", async () => {
    const user = userEvent.setup();
    const one = onField(1);
    renderAt(playPath(paths.moveMatch, { matchId: one.match.id }));

    const sheet = await screen.findByRole("dialog", {
      name: "Move this match",
    });
    await user.click(
      await within(sheet).findByRole("radio", { name: "Back to waiting" }),
    );
    await user.click(
      within(sheet).getByRole("button", { name: "Move to waiting" }),
    );

    await waitFor(() => {
      expect(runningDyp().fields.some((f) => f.match_id === one.match.id)).toBe(
        false,
      );
    });
    const players = playersOnFields();
    expect(new Set(players).size).toBe(players.length);
  });

  it("does not offer a waiting match a field while its players play (BR-131)", async () => {
    // A third, free field.
    const t = runningDyp();
    t.fields.push({ id: "field-3", number: 3, match_id: null });
    const { data: play } = await provisionalApi.GET(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/play",
      { params: { path: { league_id: DEMO_LEAGUE_ID, tournament_id: t.id } } },
    );
    const blocked = play?.waiting.find((w) => w.busy.length > 0);
    renderAt(playPath(paths.moveMatch, { matchId: blocked?.match_id ?? "" }));

    const sheet = await screen.findByRole("dialog", {
      name: "Put this match on a field",
    });
    expect(
      await within(sheet).findByRole("radio", { name: "Field 3" }),
    ).toBeDisabled();

    // The fake API refuses it too.
    const response = await provisionalApi.PUT(
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields/placements",
      {
        params: { path: { league_id: DEMO_LEAGUE_ID, tournament_id: t.id } },
        body: {
          placements: [
            {
              match_id: blocked?.match_id ?? "",
              field_id: "field-3",
              from_field_id: null,
            },
          ],
        },
      },
    );
    expect(response.response.status).toBe(422);
    expect(response.error?.code).toBe("player_on_another_field");
    expect(response.error?.detail).toHaveProperty("field_ids");
  });

  it("refuses a stale or not allowed placement like the API (ADR-008, FR-093)", async () => {
    const t = runningDyp();
    const [one, two] = t.fields;
    const path = {
      league_id: DEMO_LEAGUE_ID,
      tournament_id: t.id,
    };
    const url =
      "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/fields/placements";

    // The screen saw the match waiting, but it is on Field 1.
    const stale = await provisionalApi.PUT(url, {
      params: { path },
      body: {
        placements: [
          {
            match_id: one?.match_id ?? "",
            field_id: null,
            from_field_id: two?.id ?? null,
          },
        ],
      },
    });
    expect(stale.response.status).toBe(409);
    expect(stale.error?.code).toBe("placement_changed");

    // Two matches on fields that do not swap with each other.
    const rotation = await provisionalApi.PUT(url, {
      params: { path },
      body: {
        placements: [
          {
            match_id: one?.match_id ?? "",
            field_id: null,
            from_field_id: one?.id ?? null,
          },
          {
            match_id: two?.match_id ?? "",
            field_id: null,
            from_field_id: two?.id ?? null,
          },
        ],
      },
    });
    expect(rotation.response.status).toBe(422);
    expect(rotation.error?.code).toBe("placement_not_allowed");
  });

  it("adds a field and removes it after confirming (FR-090, BR-132)", async () => {
    const user = userEvent.setup();
    renderAt(playPath(paths.editFields));

    const sheet = await screen.findByRole("dialog", { name: "Fields" });
    await user.click(
      await within(sheet).findByRole("button", { name: /^Add a field/ }),
    );
    expect(
      await within(sheet).findByText("Field 3 added."),
    ).toBeInTheDocument();
    expect(runningDyp().fields.map((f) => f.number)).toEqual([1, 2, 3]);

    await user.click(
      within(sheet).getByRole("button", { name: "Remove Field 1" }),
    );
    const confirm = await screen.findByRole("alertdialog", {
      name: "Remove Field 1?",
    });
    await user.click(
      within(confirm).getByRole("button", { name: "Remove Field 1" }),
    );

    expect(
      await within(sheet).findByText("Field 1 removed."),
    ).toBeInTheDocument();
    expect(runningDyp().fields.map((f) => f.number)).toEqual([2, 3]);
  });

  it("adds no field beyond 32 (BR-132)", async () => {
    const t = runningDyp();
    for (let number = t.fields.length + 1; number <= 32; number++) {
      t.fields.push({ id: `field-${String(number)}`, number, match_id: null });
    }
    renderAt(playPath(paths.editFields));

    const sheet = await screen.findByRole("dialog", { name: "Fields" });
    expect(
      await within(sheet).findByRole("button", { name: /^Add a field/ }),
    ).toBeDisabled();
    expect(
      within(sheet).getByText("A tournament has at most 32 fields."),
    ).toBeInTheDocument();
  });

  it("keeps the last field (BR-132)", async () => {
    const t = runningDyp();
    t.fields = t.fields.slice(0, 1);
    renderAt(playPath(paths.editFields));

    const sheet = await screen.findByRole("dialog", { name: "Fields" });
    expect(
      await within(sheet).findByRole("button", { name: "Remove Field 1" }),
    ).toBeDisabled();
    expect(
      within(sheet).getAllByText("The last field can't be removed."),
    ).not.toHaveLength(0);
  });
});
