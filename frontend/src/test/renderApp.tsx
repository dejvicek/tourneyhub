import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter } from "react-router";

import { App } from "@/App";
import { routes } from "@/routes";

/**
 * The whole app at `path`, with a QueryClient that never retries; pass your own
 * to look into its caches.
 */
export function renderAt(
  path: string,
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  }),
) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<App router={router} queryClient={queryClient} />);
  return router;
}
