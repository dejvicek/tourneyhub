// Starts the demo's fake API in the browser. main.tsx imports this module
// dynamically and only in demo mode, so a production build contains none of
// it (src/lib/demoMode.ts).
import { delay, http } from "msw";
import { setupWorker } from "msw/browser";

import { fakeHandlers } from "@/test/fake/allHandlers";
import { TEST_EMAIL } from "@/test/fake/ids";
import { apiError, route } from "@/test/fake/route";
import { TEST_PASSWORD, TEST_SIGNUP_CODE } from "@/test/fake/seedOutside";
import { outsideDb } from "@/test/fake/store";

// Demo only: the account the login screen offers in demo mode. The tests
// never call this route; it goes with the demo (D5).
const demoAccount = route("get", "/api/v1/demo/account", () => ({
  email: TEST_EMAIL,
  password: TEST_PASSWORD,
  signup_code: outsideDb().signupCode ?? TEST_SIGNUP_CODE,
}));

export async function startDemo(): Promise<void> {
  const worker = setupWorker(
    // A realistic network delay first, so that screens show their pending
    // states; returning nothing passes the request to the next handler.
    http.all("/api/*", async () => {
      await delay();
    }),
    demoAccount,
    ...fakeHandlers,
    // An API route without a demo handler answers like the router's 404.
    http.all("/api/*", ({ request }) => {
      console.warn(`Demo: no handler for ${request.method} ${request.url}`);
      return apiError(404, "not_found", { demo: "no_handler" });
    }),
  );
  await worker.start({ onUnhandledFrame: "bypass", quiet: true });
}
