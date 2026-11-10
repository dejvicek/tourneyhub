import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { App } from "@/App";
import { i18n } from "@/i18n";
import { LANGUAGE_STORAGE_KEY } from "@/i18n/language";
import { routes } from "@/routes";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<App router={router} queryClient={new QueryClient()} />);
}

describe("App", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("shows the home page in the shell", () => {
    renderAt("/");

    expect(
      screen.getByRole("link", { name: "TourneyHub" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Welcome to TourneyHub" }),
    ).toBeInTheDocument();
  });

  it("switches the texts to Czech and remembers the choice", async () => {
    const user = userEvent.setup();
    renderAt("/");

    await user.click(screen.getByRole("button", { name: "Čeština" }));

    expect(
      await screen.findByRole("heading", {
        name: "Vítejte v aplikaci TourneyHub",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Čeština" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("group", { name: "Jazyk" })).toBeInTheDocument();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("cs");
    expect(document.documentElement.lang).toBe("cs");
  });

  it("shows the not-found page for an unknown route", () => {
    renderAt("/no/such/page");

    expect(
      screen.getByRole("heading", { name: "Page not found" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to the home page" }),
    ).toHaveAttribute("href", "/");
  });
});
