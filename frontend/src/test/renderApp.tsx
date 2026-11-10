import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter } from "react-router";

import { App } from "@/App";
import { routes } from "@/routes";

/** The whole app at `path`, with a fresh QueryClient that never retries. */
export function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(<App router={router} queryClient={queryClient} />);
  return router;
}
