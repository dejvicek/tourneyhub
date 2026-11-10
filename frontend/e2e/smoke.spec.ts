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

test("the theme follows the device's light or dark setting", async ({
  page,
}) => {
  // body takes its background from the --background token (index.css), so it
  // shows which theme is active. A probe element resolves the token itself.
  const readBackgrounds = () =>
    page.evaluate(() => {
      const probe = document.createElement("div");
      probe.style.backgroundColor = "var(--background)";
      document.body.append(probe);
      const token = getComputedStyle(probe).backgroundColor;
      probe.remove();
      return { body: getComputedStyle(document.body).backgroundColor, token };
    });

  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const light = await readBackgrounds();

  await page.emulateMedia({ colorScheme: "dark" });
  const dark = await readBackgrounds();

  expect(dark.body).not.toBe(light.body);
  expect(light.body).toBe(light.token);
  expect(dark.body).toBe(dark.token);
  expect(dark.token).not.toBe(light.token);
});
