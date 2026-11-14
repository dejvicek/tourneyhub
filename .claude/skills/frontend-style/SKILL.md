---
name: frontend-style
description: Use when planning, writing, changing or reviewing anything in TourneyHub's frontend/ — React components, screens and routes, Tailwind classes, theme tokens in index.css, shadcn/ui components, translations in src/i18n, TanStack Query queries and mutations, the API client in src/api, Vitest or Playwright tests, package.json, eslint.config.js, the tsconfigs, .prettierrc.json, vite.config.ts or pnpm-workspace.yaml — or when editing docs/style/frontend-style.md.
---

# TourneyHub frontend style

The rules live in `docs/style/frontend-style.md`. Before writing code, read the sections for what you touch (§3 TypeScript, §4 React, §5 styling and themes, §6 accessibility, §7 translations, §8 data and the API client, §9 routing, §10 tests, §11 structure). Take tool versions and configuration from `frontend/package.json`, `frontend/pnpm-lock.yaml` and `frontend/eslint.config.js`, not from memory; the guide's §2 explains the choices in them that are not obvious. Where it disagrees with `ADR.md`, the ADR wins until it is changed; the guide's §12 lists the changes it proposes.

## Project decisions an agent will not guess

| Topic | This project does |
|---|---|
| Server data | Only in TanStack Query. `queryOptions` / `mutationOptions` in a feature's `api.ts`; functions return `dataOf(api.GET(…))` and pass `signal`. Keys start with the entity (`["leagues", leagueId, …]`); a mutation has ``scope: { id: `league:${leagueId}` }`` and its `onSettled` invalidates the league's prefix. No optimistic cache writes, no `useSuspenseQuery`, no router loaders, actions or `<Form>`. |
| API client | `api` in `src/api/client.ts`, made by `createApi`, without `baseUrl` (the paths carry `/api/v1`), with one middleware that sends the Bearer token from `src/api/token.ts` and refreshes once after a 401. `fetch` only inside `src/api/`; components never import `api` or `dataOf`. `ApiError.code` is `undefined` for a body that is not the API's error shape. Types only from the generated, git-ignored `src/api/schema.d.ts`; no `as` on API data; a `switch` over error codes has no `default`. |
| Styling | Mobile-first: unprefixed classes are the phone, no `max-*` or `min-[…]` variants. Tailwind's palette is removed (`--color-*: initial`), so colours come only from theme tokens, which now exist in `index.css` and guide §5.2; a new colour needs a token there first. No `dark:` outside `src/components/ui/`. `outline-hidden`, never `outline-none`. Merge classes with `cn`, with one import path `@/lib/utils` (configured with the theme's text styles; ESLint bans importing the `cn` package elsewhere, so fix the import after `shadcn add`). No `*-black` / `*-white`, named or `color-mix()` colours outside `ui/`. |
| Themes | The theme follows `prefers-color-scheme`: light tokens in `:root`, dark ones in `@media (prefers-color-scheme: dark)`. The shadcn CLI writes dark tokens into a `.dark` block; move them into the media block. No manual theme switch. |
| shadcn/ui | Never run `shadcn init` again (it defaults to Base UI now; we are `new-york` on Radix). `pnpm exec shadcn add <name> --diff`, never `--overwrite`, `apply`, `migrate base-color` or `eject`. Edit `src/components/ui/` only for project-wide decisions; its files keep kebab-case names. Icons are our own SVG components in the `icons.tsx` files, drawn after Figma; no `lucide-react`, so replace the import that `shadcn add` generates. |
| Translations | Every user-visible string, `aria-label` included, goes through `t()`. `src/i18n/locales/en.ts` is the reference; `cs.ts` is typed `CsMessages`. Czech plurals need `_one`, `_few`, `_many`, `_other`. Dates and numbers through `Intl` with `i18n.resolvedLanguage`, never `toLocale*String`. A viewer's language comes from `pickLanguage`. |
| Accessibility | WCAG 2.2 AA in both themes. Result entry and primary phone actions are at least 44 × 44 px. ESLint uses `eslint-plugin-jsx-a11y-x` (not `jsx-a11y`); map each new copied control in `settings["jsx-a11y-x"].components`. Announce results with `role="status"` or `role="alert"`; each screen renders its own `<title>`. |
| Imports | `api`, `i18n`, `components`, `hooks`, `lib` → `features` → `pages`, `routes.tsx`, `App.tsx`, `main.tsx`. `@/` is the only alias. No barrel files. No `forwardRef`: React 19 passes `ref` as a prop. |
| Routing | React Router Data mode: `createBrowserRouter(routes)`, one table in `src/routes.tsx`. One `lazy` chunk per area; the root route has `HydrateFallback` and `ErrorBoundary`. A client `middleware` on the parent route guards organizer and admin routes. Links are built with `generatePath`. Import from `react-router`, never `react-router-dom`. |
| Tests | Vitest with jsdom: find by role, `const user = userEvent.setup()` before `render`, no `fireEvent`, no `container`. Mock the network (MSW), never the client module. Playwright: locate by role, each test creates its own data, one account per worker, locale `en-US`. |
| Toolchain | TypeScript stays on 6.0 (TypeScript 7 has no compiler API for typescript-eslint and openapi-typescript). Prettier and its Tailwind plugin are pinned exactly. pnpm 12 does not install a version younger than one day (`minimumReleaseAge`). A new ESLint plugin must declare ESLint 10 support. |

## Before you report the work as done

Run from `frontend/`, never from the repository root: `pnpm install --frozen-lockfile`, `pnpm format`, then `pnpm lint`, `pnpm format:check`, `pnpm typecheck`, `pnpm test` and `pnpm build`. Run `pnpm e2e` when a screen changed and the production images are up (ADR-013).

If a rule stops you from doing what the task needs, do not work around it. Say which rule, and propose a change to `docs/style/frontend-style.md`.
