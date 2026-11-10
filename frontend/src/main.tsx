import "@/i18n";
import "@/index.css";
// The design's fonts, self-hosted (CSP default-src 'self'): Atkinson
// Hyperlegible Next 400 and 700, Big Shoulders 800, in the Latin and Latin
// Extended subsets that English and Czech need.
import "@fontsource/atkinson-hyperlegible-next/latin-400.css";
import "@fontsource/atkinson-hyperlegible-next/latin-ext-400.css";
import "@fontsource/atkinson-hyperlegible-next/latin-700.css";
import "@fontsource/atkinson-hyperlegible-next/latin-ext-700.css";
import "@fontsource/big-shoulders/latin-800.css";
import "@fontsource/big-shoulders/latin-ext-800.css";

import { QueryClient } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";

import { ApiError } from "@/api/client";
import { App } from "@/App";
import { isDemoMode } from "@/lib/demoMode";
import { routes } from "@/routes";

// Demo mode serves the API from an MSW worker before the first request. Vite
// replaces import.meta.env.MODE with "production" in a production build, so
// the condition is false at build time, the bundler removes the branch and
// never emits the chunk of the dynamic import: MSW and src/demo stay out of
// dist. CI checks it (ci.yml, "The build contains no demo"); guide §11.
if (import.meta.env.MODE !== "production" && isDemoMode(import.meta.env)) {
  const { startDemo } = await import("@/demo/browser");
  await startDemo();
}

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html has no #root element");
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A 4xx will not change on retry; network errors and 5xx may (§8.1).
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.status < 500) && failureCount < 3,
      staleTime: 30_000,
    },
  },
});

createRoot(root).render(
  <StrictMode>
    <App router={createBrowserRouter(routes)} queryClient={queryClient} />
  </StrictMode>,
);
