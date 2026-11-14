import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      // The dev server passes /api on to the api, so the browser sees one
      // origin, as behind Caddy (ADR-004, ADR-005). compose.override.yaml
      // points it at the api service; on the host, the api's published port.
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
            // (docs/style/frontend-style.md §9).
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
