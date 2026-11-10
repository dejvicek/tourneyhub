import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { generatePath } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { setAccessToken } from "@/api/token";
import { DEMO_EMAIL, DEMO_LEAGUE_ID } from "@/demo/ids";
import { DEMO_PASSWORD, DEMO_SIGNUP_CODE } from "@/demo/seedOutside";
import { outsideDb } from "@/demo/store";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { renderAt } from "@/test/renderApp";
import { server } from "@/test/server";

import { axeViolations } from "./axeCheck";

const players = generatePath(paths.players, { leagueId: DEMO_LEAGUE_ID });

async function logIn(
  user: ReturnType<typeof userEvent.setup>,
  email: string,
  password: string,
) {
  await user.type(await screen.findByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Log in" }));
}

describe("auth screens", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    setAccessToken(null);
  });

  it("FR-003: logs in and returns to the page the guard stopped", async () => {
    outsideDb().signedInUserId = null;
    const user = userEvent.setup();
    const view = renderAt(players);

    // N8: a logged-out deep link lands on the login, with the way back.
    expect(
      await screen.findByRole("heading", { level: 1, name: "Log in" }),
    ).toBeInTheDocument();
    expect(view.state.location.search).toBe(
      `?${new URLSearchParams({ next: players }).toString()}`,
    );

    await logIn(user, DEMO_EMAIL, DEMO_PASSWORD);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Players" }),
    ).toBeInTheDocument();
    expect(view.state.location.pathname).toBe(players);
  });

  it("FR-003: a wrong password says so and stays on the login", async () => {
    const user = userEvent.setup();
    renderAt(paths.login);

    await logIn(user, DEMO_EMAIL, "not-the-password");

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "The email or password is wrong.",
      );
    });
    expect(
      screen.getByRole("heading", { level: 1, name: "Log in" }),
    ).toBeInTheDocument();
  });

  it("ADR-006: a 429 shows the wait and blocks the button until it ends", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          { code: "too_many_attempts", detail: { retry_after: 30 } },
          { status: 429, headers: { "Retry-After": "30" } },
        ),
      ),
    );
    const user = userEvent.setup();
    renderAt(paths.login);

    await logIn(user, DEMO_EMAIL, "guess");

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Too many attempts. Try again in 30 seconds.",
      );
    });
    expect(
      screen.getByRole("button", { name: "Wait 30 seconds" }),
    ).toBeDisabled();
  });

  it("FR-001: a wrong sign-up code is shown at the code", async () => {
    const user = userEvent.setup();
    renderAt(paths.signUp);

    await user.type(await screen.findByLabelText("Sign-up code"), "WRONG");
    await user.type(screen.getByLabelText("Email"), "new@example.test");
    await user.type(screen.getByLabelText("Your name"), "Nová Organizátorka");
    await user.type(
      screen.getByLabelText("Password"),
      "a long enough password",
    );
    await user.click(
      screen.getByRole("button", { name: "Create the account" }),
    );

    const code = screen.getByLabelText("Sign-up code");
    await waitFor(() => {
      expect(code).toHaveAttribute("aria-invalid", "true");
    });
    expect(code).toHaveAccessibleDescription("This sign-up code is not valid.");
  });

  it("FR-001: the right code creates the account and opens My leagues", async () => {
    const user = userEvent.setup();
    renderAt(paths.signUp);

    await user.type(
      await screen.findByLabelText("Sign-up code"),
      DEMO_SIGNUP_CODE,
    );
    await user.type(screen.getByLabelText("Email"), "new@example.test");
    await user.type(screen.getByLabelText("Your name"), "Nová Organizátorka");
    await user.type(
      screen.getByLabelText("Password"),
      "a long enough password",
    );
    await user.click(
      screen.getByRole("button", { name: "Create the account" }),
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "My leagues" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("You have no leagues yet."),
    ).toBeInTheDocument();
  });

  it("FR-002: a short password shows P2b's rule at the field", async () => {
    const user = userEvent.setup();
    renderAt(paths.signUp);

    await user.type(
      await screen.findByLabelText("Sign-up code"),
      DEMO_SIGNUP_CODE,
    );
    await user.type(screen.getByLabelText("Email"), "new@example.test");
    await user.type(screen.getByLabelText("Your name"), "Nová");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(
      screen.getByRole("button", { name: "Create the account" }),
    );

    const password = screen.getByLabelText("Password");
    await waitFor(() => {
      expect(password).toHaveAttribute("aria-invalid", "true");
    });
    expect(password).toHaveAccessibleDescription(
      /Use at least 15 characters\./,
    );
  });

  it("FR-004: the password change shows each error at its field, then succeeds", async () => {
    const user = userEvent.setup();
    renderAt(paths.changePassword);
    const current = await screen.findByLabelText("Current password");
    const next = screen.getByLabelText("New password");
    const submit = screen.getByRole("button", { name: "Change password" });

    await user.type(current, "not the current one");
    await user.type(next, "a brand new long password");
    await user.click(submit);
    await waitFor(() => {
      expect(current).toHaveAccessibleDescription(
        "The current password is wrong.",
      );
    });

    await user.clear(current);
    await user.type(current, DEMO_PASSWORD);
    await user.clear(next);
    await user.type(next, DEMO_PASSWORD);
    await user.click(submit);
    await waitFor(() => {
      expect(next).toHaveAccessibleDescription(
        /The new password must differ from the current one\./,
      );
    });
    expect(current).not.toHaveAttribute("aria-invalid");

    await user.clear(next);
    await user.type(next, "short");
    await user.click(submit);
    await waitFor(() => {
      expect(next).toHaveAccessibleDescription(/Use at least 15 characters\./);
    });

    await user.clear(next);
    await user.type(next, "a brand new long password");
    await user.click(submit);
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Password changed. Your other devices are logged out.",
      );
    });
  });

  it("logs out from the account menu and the guard then asks to log in", async () => {
    const user = userEvent.setup();
    const view = renderAt(paths.myLeagues);

    await user.click(
      await screen.findByRole("button", { name: "Account: Alex Organizer" }),
    );
    await user.click(await screen.findByRole("menuitem", { name: "Log out" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Log in" }),
    ).toBeInTheDocument();
    await view.navigate(paths.myLeagues);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Log in" }),
    ).toBeInTheDocument();
    expect(view.state.location.pathname).toBe(paths.login);
  });

  it.each([
    ["login", paths.login, "Log in"],
    ["sign-up", paths.signUp, "Sign up"],
    ["change password", paths.changePassword, "Change your password"],
  ])("the %s screen has no axe violations", async (_, path, title) => {
    renderAt(path);
    await screen.findByRole("heading", { level: 1, name: title });

    expect(await axeViolations()).toEqual([]);
  });
});
