import { expect, test } from "@playwright/test";

// The skeleton's smoke test: Caddy serves the built app and proxies /api to
// the api, on one HTTPS origin (ADR-005).

test("the app loads over HTTPS and shows the shell in English", async ({
  page,
}) => {
  await page.goto("/");

  expect(new URL(page.url()).protocol).toBe("https:");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Welcome to TourneyHub",
  );
  await expect(page.getByRole("group", { name: "Language" })).toBeVisible();
  await expect(page.getByRole("button", { name: "English" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("/api answers with the API's error shape, not index.html", async ({
  request,
}) => {
  // Any league id: without an access token the api refuses first (ADR-008).
  const response = await request.get(
    "/api/v1/leagues/019a6d4e-8f2b-7c3d-9e1f-2a3b4c5d6e7f",
  );

  expect(response.status()).toBe(401);
  expect(response.headers()["content-type"]).toBe("application/json");
  expect(await response.json()).toEqual({
    code: "not_authenticated",
    detail: {},
  });
});

test("switching to Czech changes the text and survives a reload", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Čeština" }).click();

  await expect(page.locator("html")).toHaveAttribute("lang", "cs");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Vítejte v aplikaci TourneyHub",
  );
  await expect(page.getByRole("group", { name: "Jazyk" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Vítejte v aplikaci TourneyHub",
  );
});
