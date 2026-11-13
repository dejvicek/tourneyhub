// Starts the demo's fake API in the browser. main.tsx imports this module
// dynamically and only in demo mode, so a production build contains none of
// it (src/lib/demoMode.ts).
import { delay, http } from "msw";
import { setupWorker } from "msw/browser";

import { fakeHandlers } from "@/test/fake/allHandlers";
import { apiError } from "@/test/fake/route";

export async function startDemo(): Promise<void> {
  const worker = setupWorker(
    // A realistic network delay first, so that screens show their pending
    // states; returning nothing passes the request to the next handler.
    http.all("/api/*", async () => {
      await delay();
    }),
    ...fakeHandlers,
    // An API route without a demo handler answers like the router's 404.
    http.all("/api/*", ({ request }) => {
      console.warn(`Demo: no handler for ${request.method} ${request.url}`);
      return apiError(404, "not_found", { demo: "no_handler" });
    }),
  );
  await worker.start({ onUnhandledFrame: "bypass", quiet: true });
}
