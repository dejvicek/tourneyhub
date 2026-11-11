import { QueryClient } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { setAccessToken } from "@/api/token";
import { DEMO_USER_ID } from "@/demo/ids";
import { DEMO_SIGNUP_CODE } from "@/demo/seedOutside";
import { outsideDb } from "@/demo/store";
import { axeViolations } from "@/features/auth/axeCheck";
import { i18n } from "@/i18n";
import { paths } from "@/lib/paths";
import { renderAt } from "@/test/renderApp";
import { server } from "@/test/server";

async function openAdmin() {
  const user = userEvent.setup();
  renderAt(paths.admin);
  await screen.findByRole("heading", { level: 1, name: "Administration" });
  await screen.findByText("Tomáš Černý");
  return user;
}

function row(name: string) {
  const item = screen
    .getAllByRole("listitem")
    .find((candidate) => within(candidate).queryByText(name) !== null);
  if (item === undefined) {
    throw new Error(`no list item for ${name}`);
  }
  return within(item);
}

describe("the admin area", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    setAccessToken(null);
  });

  it("FR-005: shows the sign-up code and the accounts", async () => {
    await openAdmin();

    expect(screen.getByTestId("signup-code")).toHaveTextContent(
      DEMO_SIGNUP_CODE,
    );
    expect(
      row("Eva Nováková").getByText("Must choose a new password"),
    ).toBeInTheDocument();
    expect(row("Alex Organizer").getByText("You")).toBeInTheDocument();
    expect(row("Alex Organizer").getByText("Admin")).toBeInTheDocument();
  });

  it("FR-006: the admin's own account has no reset button", async () => {
    await openAdmin();

    expect(
      row("Alex Organizer").queryByRole("button", { name: /Reset/ }),
    ).toBeNull();
    expect(
      row("Tomáš Černý").getByRole("button", {
        name: "Reset the password of Tomáš Černý",
      }),
    ).toBeInTheDocument();
  });

  it("FR-005: sets a new code and shows it", async () => {
    const user = await openAdmin();

    await user.type(
      screen.getByLabelText("New code"),
      "  Tuesday-kicker-2026 ",
    );
    await user.click(screen.getByRole("button", { name: "Save the code" }));

    await waitFor(() => {
      expect(screen.getByTestId("signup-code")).toHaveTextContent(
        "Tuesday-kicker-2026",
      );
    });
    expect(screen.getByText("The sign-up code is saved.")).toBeInTheDocument();
    expect(outsideDb().signupCode).toBe("Tuesday-kicker-2026");
    expect(screen.getByLabelText("New code")).toHaveValue("");
  });

  it("FR-005: a code that is too short is refused at the field, with no request", async () => {
    const user = await openAdmin();
    let requests = 0;
    server.use(
      http.put("/api/v1/admin/signup-code", () => {
        requests += 1;
        return HttpResponse.json({});
      }),
    );

    await user.type(screen.getByLabelText("New code"), "short");
    await user.click(screen.getByRole("button", { name: "Save the code" }));

    expect(screen.getByLabelText("New code")).toHaveAccessibleDescription(
      /Use at least 12 characters\./,
    );
    expect(requests).toBe(0);
    expect(outsideDb().signupCode).toBe(DEMO_SIGNUP_CODE);
  });

  it("FR-005: generates a code", async () => {
    const user = await openAdmin();

    await user.click(screen.getByRole("button", { name: "Generate a code" }));

    await waitFor(() => {
      expect(screen.getByTestId("signup-code")).not.toHaveTextContent(
        DEMO_SIGNUP_CODE,
      );
    });
    expect(
      screen.getByText("A new sign-up code is generated."),
    ).toBeInTheDocument();
  });

  it("FR-005: closes sign-up", async () => {
    const user = await openAdmin();

    await user.click(screen.getByRole("button", { name: "Close sign-up" }));

    expect(
      await screen.findByText(/Sign-up is closed\. Nobody can create/),
    ).toBeInTheDocument();
    expect(outsideDb().signupCode).toBeNull();
    expect(screen.queryByRole("button", { name: "Close sign-up" })).toBeNull();
  });

  it("FR-006: a generated password is shown once and gone with the dialog", async () => {
    const user = await openAdmin();

    await user.click(
      screen.getByRole("button", { name: "Reset the password of Tomáš Černý" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Reset the password of Tomáš Černý?",
    });
    expect(
      within(dialog).getByText(/is logged out on every device/),
    ).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("button", { name: "Reset password" }),
    );

    const shown = await within(dialog).findByTestId("temporary-password");
    const password = shown.textContent;
    expect(password).not.toBe("");
    await user.click(
      within(dialog).getByRole("button", { name: "Copy the password" }),
    );
    expect(await navigator.clipboard.readText()).toBe(password);

    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.body).not.toHaveTextContent(password);
    expect(
      await row("Tomáš Černý").findByText("Must choose a new password"),
    ).toBeInTheDocument();
    expect(
      outsideDb().accounts.find((a) => a.user.display_name === "Tomáš Černý")
        ?.password,
    ).toBe(password);
  });

  it("FR-006: a chosen password is checked at the field, then set and not shown", async () => {
    const user = await openAdmin();
    await user.click(
      screen.getByRole("button", { name: "Reset the password of Tomáš Černý" }),
    );
    const dialog = await screen.findByRole("dialog");

    await user.click(
      within(dialog).getByRole("radio", {
        name: "Choose a temporary password",
      }),
    );
    await user.type(
      within(dialog).getByLabelText("Temporary password"),
      "short",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Reset password" }),
    );
    expect(
      within(dialog).getByLabelText("Temporary password"),
    ).toHaveAccessibleDescription(/Use at least 15 characters\./);

    await user.clear(within(dialog).getByLabelText("Temporary password"));
    await user.type(
      within(dialog).getByLabelText("Temporary password"),
      "table football night",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Reset password" }),
    );

    expect(
      await within(dialog).findByText(
        /Tomáš Černý can log in with the password you chose/,
      ),
    ).toBeInTheDocument();
    expect(within(dialog).queryByTestId("temporary-password")).toBeNull();
  });

  it("FR-006: cancelling resets nothing", async () => {
    const user = await openAdmin();
    await user.click(
      screen.getByRole("button", { name: "Reset the password of Tomáš Černý" }),
    );

    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
      outsideDb().accounts.find((a) => a.user.display_name === "Tomáš Černý")
        ?.user.must_change_password,
    ).toBe(false);
  });

  it("FR-006: a chosen password is not kept after Cancel", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const user = userEvent.setup();
    renderAt(paths.admin, queryClient);
    await screen.findByText("Tomáš Černý");
    const opener = screen.getByRole("button", {
      name: "Reset the password of Tomáš Černý",
    });
    await user.click(opener);
    let dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("radio", {
        name: "Choose a temporary password",
      }),
    );
    await user.type(
      within(dialog).getByLabelText("Temporary password"),
      "table football night",
    );

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(opener);
    dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("radio", { name: "Generate a password" }),
    ).toBeChecked();
    await user.click(
      within(dialog).getByRole("radio", {
        name: "Choose a temporary password",
      }),
    );
    expect(within(dialog).getByLabelText("Temporary password")).toHaveValue("");
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
  });

  it("FR-006: a failed reset, then Cancel, leaves a clean dialog behind", async () => {
    server.use(
      http.post(
        "/api/v1/admin/organizers/:id/password-reset",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );
    const user = await openAdmin();
    const opener = screen.getByRole("button", {
      name: "Reset the password of Tomáš Černý",
    });
    await user.click(opener);
    let dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Reset password" }),
    );
    expect(
      await within(dialog).findByText(/That did not work/),
    ).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await user.click(opener);

    dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByText(/That did not work/)).toBeNull();
    expect(
      within(dialog).getByRole("button", { name: "Reset password" }),
    ).toBeEnabled();
  });

  it("FR-006: the dialog cannot be closed while the request is out", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post("/api/v1/admin/organizers/:id/password-reset", async () => {
        await gate;
        return HttpResponse.json({ temporary_password: "generated-once-1" });
      }),
    );
    const user = await openAdmin();
    await user.click(
      screen.getByRole("button", { name: "Reset the password of Tomáš Černý" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Reset password" }),
    );
    expect(
      await within(dialog).findByRole("button", { name: "Resetting…" }),
    ).toBeDisabled();

    await user.keyboard("{Escape}");
    // Radix makes the page behind the dialog inert; a click there is "outside".
    await userEvent
      .setup({ pointerEventsCheck: 0 })
      .pointer({ target: document.body, keys: "[MouseLeft]" });

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Cancel" }),
    ).toBeDisabled();
    expect(within(dialog).queryByRole("button", { name: "Close" })).toBeNull();

    release();
    expect(
      await within(dialog).findByTestId("temporary-password"),
    ).toHaveTextContent("generated-once-1");
  });

  it("FR-006: the mutation cache holds no password once the dialog is closed", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const user = userEvent.setup();
    renderAt(paths.admin, queryClient);
    await screen.findByText("Tomáš Černý");
    await user.click(
      screen.getByRole("button", { name: "Reset the password of Tomáš Černý" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Reset password" }),
    );
    const password = (await within(dialog).findByTestId("temporary-password"))
      .textContent;
    expect(
      JSON.stringify(
        queryClient
          .getMutationCache()
          .getAll()
          .map((m) => m.state),
      ),
    ).toContain(password);

    await user.click(within(dialog).getByRole("button", { name: "Done" }));

    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });

  it("ADR-007: another admin has no reset button, and a refusal is explained", async () => {
    server.use(
      http.get("/api/v1/admin/organizers", () =>
        HttpResponse.json([
          {
            id: "11111111-1111-7111-8111-111111111111",
            email: "second@demo.tourneyhub.test",
            display_name: "Second Admin",
            is_admin: true,
            must_change_password: false,
            created_at: "2026-09-01T10:00:00Z",
          },
          {
            id: "22222222-2222-7222-8222-222222222222",
            email: "late@demo.tourneyhub.test",
            display_name: "Late Admin",
            is_admin: false,
            must_change_password: false,
            created_at: "2026-09-02T10:00:00Z",
          },
        ]),
      ),
      http.post("/api/v1/admin/organizers/:id/password-reset", () =>
        HttpResponse.json(
          { code: "admin_target", detail: {} },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderAt(paths.admin);
    await screen.findByText("Second Admin");
    expect(
      row("Second Admin").queryByRole("button", { name: /Reset/ }),
    ).toBeNull();
    expect(
      row("Second Admin").getByText("Reset from the command line."),
    ).toBeInTheDocument();

    // an account made an admin after the list was loaded
    await user.click(
      screen.getByRole("button", { name: "Reset the password of Late Admin" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Reset password" }),
    );

    expect(
      await within(dialog).findByText(/Admins are handled on the server/),
    ).toBeInTheDocument();
  });

  it("ADR-007: an account that is not an admin sees no admin area", async () => {
    const user = userEvent.setup();
    for (const account of outsideDb().accounts) {
      account.user.is_admin = false;
    }
    renderAt(paths.admin);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Admins only" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Sign-up code")).toBeNull();
    await user.click(
      await screen.findByRole("button", { name: "Account: Alex Organizer" }),
    );
    expect(
      screen.queryByRole("menuitem", { name: "Administration" }),
    ).toBeNull();
  });

  it("ADR-007: an admin finds the admin area in the account menu", async () => {
    const user = userEvent.setup();
    renderAt(paths.myLeagues);

    await user.click(
      await screen.findByRole("button", { name: "Account: Alex Organizer" }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: "Administration" }),
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "Administration" }),
    ).toBeInTheDocument();
  });

  it("a failed load offers a retry", async () => {
    server.use(
      http.get("/api/v1/admin/organizers", () =>
        HttpResponse.json(
          { code: "internal_error", detail: {} },
          { status: 500 },
        ),
      ),
    );
    renderAt(paths.admin);

    expect(
      await screen.findByRole(
        "button",
        { name: "Try again" },
        { timeout: 4000 },
      ),
    ).toBeInTheDocument();
  });

  it("is in Czech", async () => {
    await i18n.changeLanguage("cs");
    renderAt(paths.admin);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Správa" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Registrační kód")).toBeInTheDocument();
    expect(
      await screen.findByRole("button", {
        name: "Obnovit heslo uživatele Tomáš Černý",
      }),
    ).toBeInTheDocument();
  });

  it("the admin area and the reset dialog have no axe violations", async () => {
    const user = await openAdmin();
    expect(await axeViolations()).toEqual([]);

    await user.click(
      screen.getByRole("button", { name: "Reset the password of Tomáš Černý" }),
    );
    await screen.findByRole("dialog");

    expect(await axeViolations()).toEqual([]);
  });
});

describe("the forced new password", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
    setAccessToken(null);
  });

  async function logInAsEva(user: ReturnType<typeof userEvent.setup>) {
    outsideDb().signedInUserId = null;
    const view = renderAt(paths.login);
    await user.type(
      await screen.findByLabelText("Email"),
      "eva.novakova@demo.tourneyhub.test",
    );
    await user.type(
      screen.getByLabelText("Password"),
      "temporary-password-eva",
    );
    await user.click(screen.getByRole("button", { name: "Log in" }));
    return view;
  }

  it("ADR-006: after login the account goes to the new-password screen first", async () => {
    const user = userEvent.setup();

    await logInAsEva(user);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Change your password",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Choose a new password before you go on/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My leagues" })).toBeNull();
  });

  it("ADR-006: the other areas send the account back until the password is changed", async () => {
    const user = userEvent.setup();
    const view = await logInAsEva(user);
    await screen.findByRole("heading", {
      level: 1,
      name: "Change your password",
    });

    for (const path of [paths.myLeagues, paths.admin]) {
      await view.navigate(path);
      await waitFor(() => {
        expect(view.state.location.pathname).toBe(paths.changePassword);
      });
    }
  });

  it("ADR-006: the account menu offers only the password change and log out", async () => {
    const user = userEvent.setup();
    await logInAsEva(user);

    await user.click(
      await screen.findByRole("button", { name: "Account: Eva Nováková" }),
    );

    expect(
      await screen.findByRole("menuitem", { name: "Change password" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Log out" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "My leagues" })).toBeNull();
  });

  it("ADR-006: a new password opens the other areas again", async () => {
    const user = userEvent.setup();
    await logInAsEva(user);
    await user.type(
      await screen.findByLabelText("Current password"),
      "temporary-password-eva",
    );
    await user.type(
      screen.getByLabelText("New password"),
      "my own new passphrase",
    );
    await user.click(screen.getByRole("button", { name: "Change password" }));

    const link = await screen.findByRole("link", { name: "My leagues" });
    await user.click(link);

    expect(
      await screen.findByRole("heading", { level: 1, name: "My leagues" }),
    ).toBeInTheDocument();
  });

  it("ADR-006: a 403 password_change_required sends the account to the new-password screen", async () => {
    // The admin reset the password while this tab was open.
    server.use(
      http.get("/api/v1/leagues", () => {
        const demo = outsideDb().accounts.find(
          (a) => a.user.id === DEMO_USER_ID,
        );
        if (demo) {
          demo.user.must_change_password = true;
        }
        return HttpResponse.json(
          { code: "password_change_required", detail: {} },
          { status: 403 },
        );
      }),
    );
    const view = renderAt(paths.myLeagues);

    await waitFor(() => {
      expect(view.state.location.pathname).toBe(paths.changePassword);
    });
  });
});
