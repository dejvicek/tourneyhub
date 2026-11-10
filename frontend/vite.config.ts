import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { msw } from "msw/vite";
import { loadEnv } from "vite";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  // Demo mode (src/lib/demoMode.ts): `pnpm dev:demo` (mode "demo") or
  // VITE_DEMO=true, never in a production build. Only then does MSW's plugin
  // serve its worker script, so a production build has no
  // mockServiceWorker.js. The repository ignores .env.* files, so mode "demo"
  // sets VITE_DEMO here rather than in .env.demo.
  const demo =
    mode !== "production" &&
    (mode === "demo" || loadEnv(mode, process.cwd()).VITE_DEMO === "true");

  return {
    define: demo ? { "import.meta.env.VITE_DEMO": JSON.stringify("true") } : {},
    plugins: [
      react(),
      tailwindcss(),
      ...(demo ? [msw({ mode: "worker-only" })] : []),
    ],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      // The dev server passes /api on to the api, so the browser sees one
      // origin, as behind Caddy (ADR-004, ADR-005). compose.override.yaml
      // points it at the api service; on the host, the api's published port.
      // In demo mode the MSW worker answers /api before it leaves the page.
      proxy: {
        "/api": process.env.API_PROXY_TARGET ?? "http://localhost:8000",
      },
    },
    build: {
      rolldownOptions: {
        output: {
          codeSplitting: {
            // One chunk per feature folder, the router's lazy areas: each
            // chunk is a request that can fail on a weak connection
            // (docs/frontend-style.md §9).
            groups: [
              {
                debugName: "feature areas",
                // Shared code (React, Query, i18n) stays in the common chunks.
                includeDependenciesRecursively: false,
                name: (id) =>
                  /\/src\/features\/([^/]+)\//.exec(id)?.[1] ?? null,
                test: /\/src\/features\//,
              },
            ],
          },
        },
      },
    },
    test: {
      environment: "jsdom",
      // e2e/ holds the Playwright tests, which run against the images.
      exclude: [...configDefaults.exclude, "e2e/**"],
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
      unstubGlobals: true,
    },
  };
});
