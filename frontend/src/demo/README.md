# Demo mode

`pnpm dev:demo` (or `VITE_DEMO=true pnpm dev`) runs the app against a fake API: an MSW worker in the browser answers every `/api/v1/…` request from an in-memory store. A reload starts again from the seed. A production build never contains it: `main.tsx` imports `browser.ts` dynamically, behind a `MODE !== "production"` check the bundler removes, and ESLint stops app code from importing anything here or from `src/test`.

The fake API is not in this folder. The tests own it in `src/test/fake/` (see `src/test/fake/README.md`); this folder only boots its handlers in the browser (`browser.ts`) and adds the demo-only account the login screen offers (`/api/v1/demo/account`). ESLint stops tests and `src/test` from importing anything from `src/demo`.
