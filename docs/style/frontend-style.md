# Frontend Style Guide

| | |
|---|---|
| Status | Proposed |
| Date | 2026-11-10 |
| Scope | All code in `frontend/`: the app in `src/`, its unit tests, the Playwright tests in `e2e/` and the configuration files. It applies to people and to AI agents; the Claude Code skill `.claude/skills/frontend-style` points here. |

The ADRs decide what the frontend is built from; this guide decides how its code is written. Where the two disagree, the ADR wins until it is changed; §12 lists the changes this guide proposes. Requirement IDs (FR-, BR-) refer to `PRD.md`. Source IDs in brackets, such as [Q6], refer to §13.

## 1. Principles

- **The tools are the rulebook.** What ESLint, Prettier, `tsc` and the tests check is configured in `frontend/` (§2). Each section opens with the rules its tools check, by rule ID and nothing more; every other rule written here exists because no tool checks it, and names its source.
- **Mobile-first, two themes.** Every screen is built for the phone first, and Tailwind's breakpoint prefixes add the tablet and desktop layouts; every screen exists in a light and a dark theme drawn from the theme tokens (ADR-003). The phone is the reference for FR-082.
- **Typed throughout.** `tsc` passes in strict mode on `src`, `vite.config.ts`, `i18next.config.ts` and `e2e`. API types come only from the generated schema (ADR-008). No `any` of our own; an `as` carries a comment saying why it is safe, as `dataOf` in `src/api/client.ts` does.
- **No text in code.** Every string a user sees or hears, `aria-label` included, goes through `t()` (ADR-003, §7).
- **One way per task.** Use the patterns this guide shows. A second way to do the same thing (another fetch helper, another state store) needs a reason in the pull request.
- **Business rules are cited.** Code and tests that implement a rule name its ID (`FR-082`, `BR-056`) in a comment or test name.
- **Changing a rule** is a pull request that changes this guide and the configuration together.

## 2. Toolchain

The configuration CI runs lives in `frontend/`: `package.json` (scripts and lower bounds), `eslint.config.js`, `.prettierrc.json`, `tsconfig.app.json`, `tsconfig.node.json`, `e2e/tsconfig.json`, `vite.config.ts` (Vite and Vitest), `i18next.config.ts` (the text check, §7), `e2e/playwright.config.ts` and `pnpm-workspace.yaml`. The exact versions live in `pnpm-lock.yaml`.

| Tool | Role |
|---|---|
| Node.js 26, pnpm 12 | Runtime and packages; the exact versions are in `.nvmrc`, `engines` and `packageManager` (ADR-003) |
| TypeScript 6.0 | Type check, strict, with `tsc --build` |
| ESLint 10 | Lint: typescript-eslint `strictTypeChecked` and `stylisticTypeChecked`, react-hooks `recommended`, react-refresh `vite`, jsx-a11y-x `strict`, better-tailwindcss, simple-import-sort, TanStack Query `flat/recommended-strict`, Testing Library `flat/react`, Playwright `flat/recommended` |
| i18next-cli 1.87 | `i18next-cli lint`, run by `pnpm lint`: user-facing text outside `t()` and `<Trans>` (§7) |
| Prettier 3.9 | Format, with prettier-plugin-tailwindcss for class order |
| Vite 8 | Dev server and build |
| Vitest 5, jsdom, Testing Library | Unit and component tests (§10) |
| Playwright | End-to-end tests against the production images (§10, ADR-013) |

Run every command from `frontend/`:

```sh
pnpm install --frozen-lockfile   # exactly what pnpm-lock.yaml says
pnpm audit --prod                # known vulnerabilities in the production dependencies; CI fails on one
pnpm format                      # eslint --fix, then prettier --write
pnpm lint                        # eslint --max-warnings=0, then i18next-cli lint
pnpm typecheck                   # tsc --build over src, the two config files and e2e
pnpm test
pnpm build
pnpm e2e                         # needs the production images running (ADR-013)
```

`dev`, `build`, `typecheck`, `lint`, `format` and `test` run `generate:api` first, which writes `src/api/schema.d.ts` from `../backend/openapi.json` (ADR-008). CI (`.github/workflows/ci.yml`) runs `pnpm install --frozen-lockfile`, then `pnpm audit --prod`, `generate:api`, `lint`, `format:check`, `typecheck`, `test` and `build`.

Choices in the configuration that are not obvious:
- `typescript` stays on `~6.0`. TypeScript 7 ships no compiler API [T1], and both typescript-eslint, which supports `>=4.8.4 <6.1.0` [T2], and openapi-typescript (ADR-008) import it. openapi-typescript 7.13 declares `typescript ^5`; `peerDependencyRules` in `pnpm-workspace.yaml` lets it run on 6.
- The tsconfigs differ from create-vite's `react-ts` template [T10] in these: `strict`, `noUncheckedIndexedAccess` and `noUncheckedSideEffectImports` are on, `paths` maps `@/*` without `baseUrl`, which TypeScript 6 deprecates [T3], `allowArbitraryExtensions` is omitted, and `noUnusedLocals` and `noUnusedParameters` are off (next item). Nothing needs `ignoreDeprecations`.
- `exactOptionalPropertyTypes` stays off: copied shadcn/ui components fail to compile with it [T4].
- `noUnusedLocals` and `noUnusedParameters` are off. `@typescript-eslint/no-unused-vars` reports unused names alone, as typescript-eslint recommends [T7].
- `generate:api` passes no `--enum` [T8]: ADR-008's error codes come out as string-literal unions, which `erasableSyntaxOnly` allows and a `switch` can check.
- ESLint has no `eslint-plugin-react`, and uses `eslint-plugin-jsx-a11y-x` instead of `eslint-plugin-jsx-a11y`. The upstream plugins' releases do not accept ESLint 10 [E10]; every plugin here does (§13).
- `jsx-a11y-x/control-has-associated-label` is on, though neither of the plugin's configs enables it. `settings["jsx-a11y-x"].components` maps each copied component that renders a native control (today `Button`).
- typescript-eslint's strict preset is not semver-stable [E2]: reports that an upgrade adds are fixed in the upgrade's pull request.
- react-refresh skips `src/components/ui/`, whose files export their variants next to the component (`buttonVariants`).
- better-tailwindcss reads the theme from `src/index.css`. Its `enforce-consistent-class-order` and `enforce-consistent-line-wrapping` stay off, because Prettier owns both.
- `index.css` sets `--color-*: initial`. Tailwind's palette is gone, so a class such as `bg-red-500` does not exist [W3] and `no-unknown-classes` fails on it. Black and white keep Tailwind's own values for the copied components; `no-restricted-classes` bans `*-black` and `*-white` outside `src/components/ui/`.
- `no-restricted-imports` has one block per folder (§11), and each block repeats the full list of banned imports, because a later block replaces the options of an earlier one. `no-restricted-syntax` works the same way: `src/routes.tsx`, `src/main.tsx`, the tests and the demo each have a block that lists every selector group it keeps.
- `linterOptions` reports an unused `eslint-disable` comment and unused inline configuration as errors, and `--max-warnings=0` fails on warnings, such as `react-hooks/exhaustive-deps`. An `eslint-disable` names its rules and gives a reason after ` -- ` [E3]; `src/test/disableComments.test.ts` checks this, and that `react-hooks/exhaustive-deps` is never disabled.
- Prettier and prettier-plugin-tailwindcss are pinned exactly, since both decide the output [E4], and are upgraded in a pull request that reformats the code. Every Prettier option stays at its default [E5]; `.prettierrc.json` holds the plugin, which must load last [E7], and its two options, `tailwindStylesheet` and `tailwindFunctions`. Prettier reads `.gitignore` [E8], so `.prettierignore` lists only `pnpm-lock.yaml`. No `eslint-plugin-prettier` or `prettier-eslint` [E6]; the presets have no formatting rules, so `eslint-config-prettier` is not needed.
- `pnpm audit --prod` checks only `dependencies` and `optionalDependencies`, what ships to the browser, and fails the CI job on any advisory [E18]. An advisory the project accepts goes in `audit.ignore` in `pnpm-workspace.yaml`, as its `GHSA-…` id with a comment that links an issue. Dev dependencies are not audited; Dependabot's weekly updates cover them.
- `format` runs `eslint --fix` before `prettier --write`, so that Prettier formats what the import sort moved.
- Every pnpm setting is in `pnpm-workspace.yaml`; `.npmrc` would hold only auth or registry. `allowBuilds` is the reviewed list for install scripts. It allows none today and denies `@swc/core`, which i18next-cli needs, because that postinstall only checks the native binary [E12]. `strictDepBuilds`, `minimumReleaseAge` (one day) and `blockExoticSubdeps` keep pnpm 12's defaults [E11]: a version published less than a day ago is not installed. `engineStrict: true` fails an install on any Node.js other than `engines` [E13], so a Node.js bump changes `.nvmrc`, `engines`, the Dockerfile and the README together.
- `@vitejs/plugin-react` 6 needs no Babel [E15]. The React Compiler is not on.
- Vitest's configuration is the `test` block of `vite.config.ts`; a `vitest.config.ts` would replace it [V4]. Vitest 5 writes reports to `.vitest/` [E14], which is git-ignored.

## 3. TypeScript

Checked by tools: `tsc` (`strict`, `noUncheckedIndexedAccess`, `erasableSyntaxOnly`, `verbatimModuleSyntax`); ESLint `@typescript-eslint/switch-exhaustiveness-check` (no `default` in a `switch` over a union), `@typescript-eslint/no-import-type-side-effects` [T5], `@typescript-eslint/ban-ts-comment`, `@typescript-eslint/no-non-null-assertion`, `@typescript-eslint/no-explicit-any`, `@typescript-eslint/no-deprecated`, `@typescript-eslint/no-unused-vars`.

- A closed set of values is a string-literal union, or an `as const` array with a type derived from it, as `LANGUAGES` and `Language` in `src/i18n/language.ts` [T9].
- Typed constant tables (query-key factories, route paths, the map from error code to message, `cva` variants) use `satisfies`, not an annotation or `as`. It checks the shape and keeps the literal types [T6].

  ```ts
  // Wrong: the annotation widens each value to string, and a typo in a code still compiles
  const CODE_TEXTS: Record<string, string> = {
    last_field: "fields.errors.lastField",
  };
  // Right: the keys are checked against ErrorCode, and the values stay literal keys for t()
  const CODE_TEXTS = {
    last_field: "fields.errors.lastField",
  } as const satisfies Partial<Record<ErrorCode, string>>;
  ```

- An `as` says in a comment why it is safe (API data: §8.2). ESLint `no-restricted-syntax` reports every `as` except `as const` and `as CSSProperties` (§5.1), so the comment is an `eslint-disable-next-line no-restricted-syntax -- <why>`, as in `dataOf`.

## 4. React

Checked by tools: ESLint react-hooks `recommended` (among them `rules-of-hooks`, `exhaustive-deps`, `static-components`, `purity`, `refs`, `set-state-in-render`, `set-state-in-effect`) [R9], `react-refresh/only-export-components` [R10], `no-restricted-syntax` (`forwardRef`, imported or as `React.forwardRef` [R2]); `react-hooks/component-hook-factories` is a no-op since 7.1 and is not listed, `@typescript-eslint/no-misused-promises`, `@typescript-eslint/no-floating-promises`.

- The root renders inside `<StrictMode>`, in `src/main.tsx` [R1].
- Server data lives only in TanStack Query (§8). Read it with the query hook where it is needed; never copy it into `useState`, context or a module variable [R3].

  ```tsx
  // Wrong: the copy goes stale when a write or a 409 reloads the league
  const { data } = useQuery(leagueQueries.detail(leagueId));
  const [league, setLeague] = useState(data);
  useEffect(() => setLeague(data), [data]);
  // Right: read the query where it is needed. A form that edits the league gets it
  // as a prop once loaded and keeps only its draft: useState(league.name)
  const { data: league } = useQuery(leagueQueries.detail(leagueId));
  ```

- Client state lives in the lowest component that owns it and moves up only when it is shared. Context holds app-wide values only: language, session [R4].
- An effect's dependencies are never suppressed. A value the effect reads but must not react to goes through `useEffectEvent` [R5].
- `use()` reads context only, never a promise of API data [R6].
- An event handler starts async work with `mutation.mutate(…)`, or marks with `void` a promise whose failure needs no handling, as `LanguageSwitch` does with `i18n.changeLanguage` [E1].
- Optimistic UI follows §8.1 [R7].
- Forms use no form library and no client-side schema: a form keeps its fields in component state or reads them from `FormData`, submits with `mutation.mutate`, and shows the server's 422 next to the field (ADR-008). A check only the browser can make, such as two password fields matching, is plain code in the handler. The server is the validator, and a schema in the browser would copy the API contract by hand (ADR-008). Revisit if a form needs cross-field rules the server cannot report per field. ESLint `no-restricted-imports` bans `react-hook-form` and `zod`.
- A component file is named after its component in PascalCase (`AppShell.tsx`), a hook file after its hook (`useLeague.ts`). `src/components/ui/` and the files the shadcn CLI writes into `src/hooks/` keep its kebab-case names [R8].

## 5. Styling

### 5.1 Tailwind

Checked by tools: ESLint better-tailwindcss `no-unknown-classes`, `no-conflicting-classes`, `no-duplicate-classes`, `no-deprecated-classes`, `no-concatenated-classes`, `enforce-consistent-variable-syntax` (`bg-(--x)`) and `no-restricted-classes` (`max-*` and arbitrary `min-[…]` breakpoint variants, the `!` modifier, `outline-none` [W20] and a translucent ring, `ring-ring/…` or `outline-ring/…` (§5.2), everywhere; `dark:`, `*-black`, `*-white` and arbitrary, named or `color-mix()` colour values outside `src/components/ui/`) [W22]; Prettier with prettier-plugin-tailwindcss (class order, inside `cn()` and `cva()` too).

- Tailwind runs through `@tailwindcss/vite` from one CSS entry, `src/index.css`; there is no `tailwind.config.js`. No Sass, Less, Stylus or CSS modules [W1].
- A token that needs utilities goes in `@theme`; a plain CSS variable goes in `:root` [W2].
- Mobile-first (ADR-003): unprefixed classes are the phone layout, and `sm:`, `md:` and `lg:` add the tablet and desktop layouts of the Figma frames [W5]. Breakpoints come only from the theme, Tailwind's or `--breakpoint-*` in rem.
- A component shown at several widths, such as a match card in a bracket and in a list, uses container queries (`@container`, `@md:`) rather than viewport breakpoints [W6].
- An arbitrary value is for a one-off no token covers, such as a `calc()` over tokens or a grid template. A value used twice becomes a token [W7].
- A value from the API reaches CSS through an inline `style` that sets a CSS variable, read as `bg-(--x)` [W8].
- App components expose variant props. `className` is for outer layout only (margin, width, grid placement) and is merged with `cn` [W9].
- Styles are reused by making a component, not with `@apply`, which appears only in `@layer base` of `index.css` [W10].
- CSS uses `var(--…)` and `--alpha()`, never `theme()` [W11].
- The browser floor is Tailwind 4's: Chrome 111, Safari 16.4, Firefox 128 [E16]. Vite's default build target lies within it [E17]. CSS or JavaScript newer than the floor, such as `light-dark()`, needs a fallback.

### 5.2 Themes

- The theme follows `prefers-color-scheme` (ADR-003). `:root` holds the light tokens, `@media (prefers-color-scheme: dark)` the dark ones, and Tailwind's default `dark:` variant uses the same query. The MVP has no manual switch [W21].
- `@theme inline` maps each token once for both themes. `index.html` declares `<meta name="color-scheme" content="light dark">` and `:root` sets `color-scheme`, so native controls and scrollbars follow the theme [W4].
- A new token is a pair, `x` and `x-foreground`, defined in both theme blocks and mapped in `@theme inline` [W14]. Its values come from the Figma design's variables; a colour the design lacks is added only with its contrast ratios recorded below.
- `index.css` maps the design's variables to the shadcn tokens and adds its extras: `team-a`, `team-b`, `notice-info`, `notice-warning`, `nav`, `nav-active`, `field` (the playfield), `feature` (the Feature button on it), `border-surface`, `input-background`, `bead-empty` and `bead-rod` (the last two are a fill and a stroke, not a pair).
- Fonts are self-hosted from `@fontsource`, because the CSP is `default-src 'self'`: Atkinson Hyperlegible Next 400 and 700 (`font-sans`, body and UI) and Big Shoulders 800 (`font-display`, titles and scores), Latin and Latin Extended only. The Figma text styles are `text-display-*`, `text-score-*`, `text-body-*`, `text-button-*`, `text-caption` and `text-micro`, each with its line height and weight.
- `index.html` has one `<meta name="theme-color">` per scheme, with `media="(prefers-color-scheme: …)"` and the `--nav` colour, `#ffffff` and `#151e28`, the colour of the header under the status bar [A22]. Contrast and focus are checked in both themes (§6).
- The design has no destructive, focus or chart colours. These were added (ratios against page, card and, for the ring, the nav's active fill; light / dark):

  | Token | Light | Dark | Ratios |
  |---|---|---|---|
  | `destructive` / `-foreground` | `#b42318` / `#ffffff` | `#ff9c8f` / `#1a2430` | text on page 5.94 / 7.77, on card 6.57 / 6.56; foreground on fill 6.57 / 7.77 |
  | `ring` | `#1e7a4c` (primary) | `#edf2f6` (primary) | page 4.81 / 13.92, card 5.33 / 11.76, nav active 4.44 / 10.30 |
  | `chart-1`…`5` | `#1e7a4c` `#e36414` `#2251c9` `#4e6157` `#7a3409` | `#5cc98a` `#f4b740` `#74b9f0` `#a9b8c6` `#f6d9a6` | on card, at least 3.44 / 6.27 |
  | `team-a-foreground`, `team-b-foreground` | `#1a2430`, `#ffffff` | `#1a2430`, `#1a2430` | on the team colour 4.56 / 8.73, 6.80 / 7.42 |
  | `field` / `-foreground` | `#1e7a4c` / `#ffffff` | `#1d5a3c` / `#edf2f6`, **provisional** | foreground on field 5.33 / 7.22; field against page 4.81 / 1.93 |
  | `feature` / `-foreground` | `#ffffff` / `#1e3327` | `#edf2f6` / `#1a2430`, **provisional** | foreground on fill 13.48 / 13.92; the button against the field 5.33 / 7.22 |

  Light `field` and `feature` are the design's `field/bg` and `feature/button`; `feature-foreground` is `text/default`, the design's bold label. The design has no dark `field/bg` or `feature/button` (the dark playfield looked transparent), so both dark pairs are provisional until it does: a darker green of the same hue, and the dark primary pair. In the dark theme the field is only 1.93 against the page, so the playfield's edge is not what tells a control apart; the Feature button on it is 7.22. A focus ring on the field relies on its background-coloured offset: the light ring is the field's own green.

- The ring is solid, never `ring/50`, with a 2 px offset in the background colour (technique C40), so it keeps 3:1 next to a primary button of the same colour; `src/components/ui/button.tsx` and the base layer were changed for it. The destructive Button uses its token pair instead of `text-white` and `dark:bg-destructive/60`.
- Deviations from Figma. The design falls below WCAG 2.2 AA in four places. Three tokens moved, each keeping its hue (HSL hue and saturation) and changing only lightness; ratios measured with a script (WCAG relative luminance), light / dark:

  | Token | Figma | Now | Ratios |
  |---|---|---|---|
  | `input` (border) | `#8fa197` / `#5b6f84` | `#7b9085` / `#657c93` | on `input-background` 3.40 / 3.07, on page 3.08 / 3.63 (was 2.72 / 2.56 on the field, 2.46 on the light page) |
  | `bead-rod` | `#8fa197` light (dark `#5b6f84` unchanged, 3.03 on `bead-empty`) | `#85988d` light | on `bead-empty` 3.06 (was 2.72) |
  | `nav-active-foreground` | `#1e7a4c` light (dark unchanged) | `#1e784b` light | on `nav-active` 4.56 (was 4.44, for 13 px text) |

  The design maps `secondary-foreground`, `accent-foreground` and `sidebar-accent-foreground` to the same light green as `nav-active-foreground` (`#1e7a4c` on `#e3ede6`, 4.44), so they move with it to `#1e784b` (4.56 on `secondary`, `accent` and `sidebar-accent`); dark values are unchanged.

  `team-a` keeps `#e36414` / `#f4b740`: light `team-a` is 3.44 on a white card and 3.11 on the page, so as text it is for large text only (3:1), that is scores (`text-score-*`, `text-display-*`). The dark `team-a` is 7.38 on a card and `team-b` passes everywhere (6.80 / 6.27 on a card), but the rule is the same for both so the sides can be swapped. Smaller text (names, labels, captions) uses `team-a-foreground` or `team-b-foreground`, or the ordinary text tokens, never the team colour; the colour is carried by a dot or border next to it.

### 5.3 shadcn/ui

- `components.json` stays as it is: style `new-york` on Radix (`radix-ui`), `cssVariables: true`, `rsc: false`. Never run `shadcn init` again: it now defaults to Base UI [W12], and the style cannot change after initialisation [W13].
- Run the CLI as `pnpm exec shadcn …`, the version in the lockfile, never `dlx shadcn@latest`. Never `shadcn eject`, which removes the `shadcn` package that `index.css` imports [W16].
- The CLI writes dark tokens only under a `.dark` selector (shadcn 4, `dist/index.js`). After `shadcn add`, move any `.dark` tokens into the `@media (prefers-color-scheme: dark)` block, or the dark theme never sees them.
- `src/components/ui/` is our code [W17]. Edit it in place only for project-wide decisions (touch sizes, focus ring, `outline-hidden`); a variant one feature needs is a wrapper component outside `ui/`.
- To update a component, review upstream with `pnpm exec shadcn add <name> --diff` and port the changes by hand; never `--overwrite` an edited file [W18].
- Never run `shadcn apply` or `shadcn migrate base-color`; both rewrite the theme [W19].
- Classes are merged with `cn`, with one import path, `@/lib/utils` [W15]. `src/lib/utils.ts`, the path `components.json` names as its `utils` alias, builds it with `createCn` from the `cn` package and registers the theme's text styles (`text-display-*`, `text-score-*`, `text-body-*`, `text-button-*`, `text-caption`, `text-micro`) as font sizes; unconfigured, `cn` takes `text-caption` for a colour and drops `text-muted-foreground` beside it. ESLint `no-restricted-imports` allows the `cn` package only in that file, so after `shadcn add` the generated `import { cn } from "cn"` becomes `@/lib/utils`. A new text style in `index.css` is added to its list.
- Icons come only from `lucide-react`, the `iconLibrary` of `components.json`. The package is not installed until an icon uses it; the pull request that renders the first icon adds it.

## 6. Accessibility

Checked by tools: ESLint jsx-a11y-x `strict` and `jsx-a11y-x/control-has-associated-label` [E9]; better-tailwindcss `no-restricted-classes` (`outline-none`).

- The target is WCAG 2.2 Level AA on every screen, in both themes [A1]; ADR-013 names it as what the axe report measures and what the gate requires from RM-11.
- Every pointer target is at least 24 × 24 CSS px (WCAG 2.5.8, Level AA) [A19]. Result entry (open the match, choose the result, save, FR-082) and the primary actions on a phone are at least 44 × 44, beyond AA on purpose: 2.5.5 is Level AAA [A2]. `Button` follows the Figma Button (`components.md`) and has no size below 44 px: `default` is the Compact button (44 px, radius 8), `lg` the Primary one (56 px, radius 10, Button/Large), `icon` 44 × 44, the `feature` variant the white 52 px button on the playfield and `text` the plain text button.
- Text contrast is at least 4.5:1 (3:1 for large text), and component boundaries and focus indicators at least 3:1, in each theme [A3]. The `--ring` token keeps 3:1 against its neighbours (§5.2) [A4].
- A sticky header or bottom bar never hides the focused element: give the page `scroll-padding` equal to the bar's height [A5]. A fixed bottom bar adds `env(safe-area-inset-bottom)` to its bottom padding, so the home indicator does not cover its buttons [A20].
- Our animations use `motion-safe:`. The reduced-motion rule in `index.css` cuts those that shadcn/ui and tw-animate-css ship [A6].
- Every screen renders its own `<title>`, one at a time [A7]. `DocumentTitle` renders it as "Screen · TourneyHub"; `index.html` has none.
- Forms use shadcn's `Field`. After validation fails, the control gets `aria-invalid="true"` and `aria-describedby` pointing at the message, which is text in `FieldError`, never colour alone; before validation there is no `aria-invalid` [A8]. Messages are the translated ADR-008 codes, and each form has a Vitest test of this.
- "Result saved", the reload after a 409 and error summaries are announced with `role="status"` or `role="alert"` [A9].
- Landmarks are HTML elements: one `<main>`, plus `<header>`, `<nav>` and `<footer>`, with all content inside one, as in `AppShell` [A10].
- `<html lang>` follows the UI language (`src/i18n/index.ts`). Knockout names are technical terms (FR-080) and take no `lang="en"` [A11].
- Anything done by dragging, such as reordering seeds, also works with single taps [A12].
- Login, sign-up and password fields allow paste and password managers: the right `type` and `autocomplete` (`username`, `current-password`, `new-password`) [A13].
- Score inputs use `inputMode="numeric"`, so a phone shows a digit keyboard (FR-082) [A14]. Text inputs are at least 16 px (`text-base`) on a phone, or iOS Safari zooms the page on focus [A21].
- Every screen works at 320 CSS px wide without horizontal scrolling; brackets and data tables may scroll in two dimensions [A15]. Playwright checks it once the mobile projects exist (ADR-013).
- With the first real screens (ADR-013), Playwright runs axe as a report, not a gate, until RM-11, through one shared fixture, `withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])`, on each main screen in both colour schemes, which one test switches with `page.emulateMedia({ colorScheme })`, not a second project [A16]. `target-size` is disabled by default [A17], so the fixture enables it by name, and its first test shows that the rule ran. It checks the 24 px of 2.5.8; the 44 px of 2.5.5 is asserted by the FR-082 scenario. Each `disableRules` entry links an issue.
- Each new screen gets a manual pass before merge: keyboard only, both themes, 320 px. A screen reader on a phone and forced colours are checked once before the pilot [A18].

## 7. Translations

Checked by tools: `tsc` (keys of `t()` through `CustomTypeOptions` in `src/i18n/i18next.d.ts`; `cs` has every key of `en`, and no other, through its `CsMessages` type); ESLint `no-restricted-properties` (`toLocaleString`, `toLocaleDateString`, `toLocaleTimeString`), `no-restricted-syntax` (an `Intl` constructor without a locale or with a literal one; `dangerouslySetInnerHTML`), `no-restricted-imports` (`i18next-browser-languagedetector`); `i18next-cli lint`, part of `pnpm lint`, for user-facing text in JSX elements and attributes outside `t()` and `<Trans>` [I1].

- No hard-coded user-facing text (ADR-003), `aria-label` and `alt` included. A line that is not user-facing, such as a product name, is excused with `i18next-instrument-ignore-next-line` and a reason after ` -- `, as with `eslint-disable`. If the linter gives a false positive that neither `i18next.config.ts` nor that comment can silence, the pull request that hits it downgrades the check to a report and says so here.
- `i18next-cli lint` sees only JSX. A string that reaches the screen another way, through state, a prop or a function's return value, goes through `t()` too.

  ```tsx
  // Wrong: the linter does not see these, and Czech readers get English
  setStatus(`Field ${String(field.number)} added`);
  return { label: "Remove", tone: "destructive" };
  // Right
  setStatus(t("fields.edit.added", { number: field.number }));
  return { label: t("players.remove.action"), tone: "destructive" };
  ```
- Texts live in `src/i18n/locales/en.ts`, the reference from which the key types come [I2], and `cs.ts`, in one namespace. Each area keeps its texts in its own module, `en/<area>.ts` and `cs/<area>.ts`, which `en.ts` and `cs.ts` merge; a `cs` module is typed `CsMessages<Messages["<area>"]>`. Keys are semantic and nested by area (`notFound.home`), never English sentences.
- A sentence is one key with `{{placeholders}}`, never pieces joined in code. `escapeValue: false` is safe because React escapes what it renders; `t()` output never goes into `dangerouslySetInnerHTML` [I3].
- Markup inside a sentence, such as a link, uses `<Trans>` with named components [I4].
- Plurals pass `count` [I5]. English keys take `_one` and `_other`; Czech takes `_one`, `_few` (2–4), `_many` (decimals) and `_other` [I6]. `CsMessages` (in `en.ts`) allows `_few` and `_many` for every key whose English reference has `_one` or `_other`, and no other extra key.
- Places in a standing are numbers, written "1." in Czech; no `ordinal` plurals [I6].
- Dates and numbers go through `Intl` with `i18n.resolvedLanguage`, or through i18next's `{{val, datetime}}` and `{{val, number}}` inside a sentence (FR-081) [I7].
- A viewer's language comes from `pickLanguage` in `src/i18n/language.ts`: their stored choice, else `navigator.language` if it is English or Czech, else English. An organizer's comes from `users.language`, and changing it saves through the API before `i18n.changeLanguage` (ADR-003). No language-detector plugin; `supportedLngs` and `fallbackLng: "en"` stay set [I8].
- API errors are shown from an `errors` object with one key per generated `ErrorCode` and `detail` as its values; `satisfies Record<ErrorCode, string>` makes a new code in `openapi.json` a type error (ADR-008) [T6].
- Knockout option names (FR-080) are keys too, with the same value in both languages.

## 8. Data

### 8.1 TanStack Query

Checked by tools: ESLint TanStack Query `flat/recommended-strict` (`prefer-query-options`, `exhaustive-deps`, `stable-query-client`, `no-void-query-fn`, `no-unstable-deps`, `mutation-property-order`, `infinite-query-property-order`) and `@tanstack/query/no-rest-destructuring` as an error; `no-restricted-imports` (`useSuspenseQuery`, `useSuspenseQueries`, `useSuspenseInfiniteQuery` [Q11]); `no-restricted-syntax` (`useOptimistic`, `setQueryData`, `setQueriesData` and `onMutate` [R7]; `new QueryClient` outside `src/main.tsx` and the tests); `@typescript-eslint/no-deprecated` (the prefetch methods that `queryClient.query` replaces).

- Queries and mutations are defined with `queryOptions` and `mutationOptions` in their feature's `api.ts`, such as `leagueQueries.detail(id)`, and components call `useQuery(leagueQueries.detail(id))` [Q1].
- Keys go from general to specific and start with the entity: `["leagues", leagueId]`, then `["leagues", leagueId, "tournaments", tournamentId]`; share-link views start with `["public", shareToken]`. One `invalidateQueries` on the league's prefix then reloads all that a write or a 409 touched (ADR-008) [Q2].
- Query and mutation functions return `dataOf(api.GET(…))`, which throws an `ApiError` for any response that is not 2xx; Query sees only a throw as a failure [Q3].
- The first query registers the error type once, `Register { defaultError: ApiError }`, next to `ApiError` in `src/api/client.ts` [Q4].
- Query functions pass their `signal` to the API call [Q5].
- There is one `QueryClient`, created in `src/main.tsx`. With the first query it gets two defaults: `retry` is a function that never retries an `ApiError` with a 4xx status and retries network errors and 5xx up to three times [Q6], and `staleTime` is 30 seconds, a starting value to tune with real use, so moving between a tournament's views does not refetch, while a viewer who comes back to the tab later does [Q7].
- A mutation's `onSettled` returns `queryClient.invalidateQueries` on the league's prefix: success, 409 and a 404 from a repeated delete all end in a reload, and `isPending` lasts until the fresh data is in (ADR-008) [Q8].
- No optimistic cache writes (`onMutate` with `setQueryData`) and no `useOptimistic`: standings, brackets and points come from the server (ADR-009). Optimistic UI renders `mutation.variables` while the mutation is pending [R7].
- Every mutation of a league has ``scope: { id: `league:${leagueId}` }``, so writes reach the server in the order the organizer made them [Q9].

  ```ts
  // Wrong: two quick saves can reach the server in either order
  renameSeason: (queryClient: QueryClient, leagueId: string) =>
    mutationOptions({
      mutationFn: (input: { seasonId: string; name: string | null }) =>
        dataOf(api.PUT("/api/v1/leagues/{league_id}/seasons/{season_id}/name", /* … */)),
      onSettled: reload(queryClient, leagueId),
    }),
  // Right: the league's writes run one after another
      onSettled: reload(queryClient, leagueId),
      scope: { id: `league:${leagueId}` },
  ```
- `networkMode` stays `online`. A paused query (`fetchStatus === "paused"`) or mutation (`isPaused`) shows that it waits for the connection, not a spinner [Q10].
- Screens render the pending, paused and error states themselves, errors inline. Only a screen's main resource uses `throwOnError`, which hands the error to the route's `ErrorBoundary` (§9) [Q12].
- Reactions the whole app shares live once, in the `onError` of `QueryCache` and `MutationCache`: 403 `password_change_required` opens the new-password screen (ADR-006); 409, and 404 from a delete, say that the data changed elsewhere and was reloaded. A 422 is shown by the form that sent it, built from `code` and `detail` [Q13].
- Cache work (invalidation) goes in `mutationOptions`; UI work (closing a dialog, navigating) goes in `mutate(vars, { onSuccess })`, which does not run once the component has unmounted [Q14].

  ```tsx
  // Wrong: the reload is lost if the sheet unmounts first, and runs only on success
  add.mutate(name, {
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["leagues", leagueId] }),
  });
  // Right: playerMutations.add's onSettled reloads the league; the call does the UI
  add.mutate(name, {
    onSuccess: (player) => {
      setName("");
      onDone(t("players.add.added", { name: player.name }));
    },
  });
  ```

### 8.2 API client

Checked by tools: `tsc` (paths, parameters and bodies against `schema.d.ts`; `noUncheckedIndexedAccess`); ESLint `no-restricted-globals` (`fetch`, also through `window` and `globalThis`, outside `src/api/`), `no-restricted-imports` (`api`, `createApi` and `dataOf` only in `src/api/` and a feature's `api.ts`; `axios` and `openapi-react-query` everywhere), `no-restricted-syntax` (every `as` except `as const` and `as CSSProperties`, outside `src/demo/`), `@typescript-eslint/switch-exhaustiveness-check` (error codes).

- The runtime client is openapi-fetch, typed by openapi-typescript (ADR-008). No axios, no other generator and no openapi-react-query, whose keys `[method, path, init]` cannot be invalidated by a league's prefix [Q15].
- `src/api/schema.d.ts` is generated by `pnpm generate:api`, git-ignored and never edited (ADR-008).
- There is one client for the generated routes, `api` in `src/api/client.ts`, on the page's own origin (ADR-005). The paths in `openapi.json` already start with `/api/v1`, so it has no `baseUrl`. Routes the backend does not have yet go through `provisionalApi` (`src/api/provisional.ts`), typed by the demo's contract (ADR-008); both are made by `createApi`.
- `dataOf()` turns openapi-fetch's `{ error }` into a thrown `ApiError` with `status`, `code` and `detail` [Q16]. `code` is `undefined` when the body is not the API's error shape, such as a proxy's error page, so a `switch` on it handles `undefined` as well.
- Authentication lives in one openapi-fetch middleware that `createApi` adds to every client, `api` and `provisionalApi` alike (ADR-006, ADR-008). It sends the token as `Authorization: Bearer`; after a 401 from any route but `/auth/login`, `/auth/refresh` and `/auth/logout` it awaits the one `POST /api/v1/auth/refresh` in flight for the tab and sends a clone of the request once more. 403 never refreshes. A refused refresh clears the token and calls the `onSessionEnded` listeners, which go to the login; a network failure during the refresh rejects like any request and keeps the session [Q17].
- The access token lives in `src/api/token.ts` (`getAccessToken`, `setAccessToken`, `onSessionEnded`), a module variable, never in `localStorage`, React state or the query cache (ADR-006) [Q18].
- Request and response types come only from the generated `paths` and `components`: no `as` on API data and no copied interfaces (ADR-008) [Q19].

## 9. Routing

Checked by tools: ESLint `no-restricted-imports` (`Form`, `useActionData`, `useFetcher`, `useFetchers`, `useLoaderData`, `useRouteLoaderData`, `useSubmit` and any `unstable_*` from `react-router` [N11]; `react-router-dom` [N12]), `no-restricted-syntax` (`loader`, `action` and `shouldRevalidate` in `src/routes.tsx`; a template literal or a `+` on a string that starts with `/` [N9]); `@typescript-eslint/no-non-null-assertion`.

- React Router runs in Data mode: `createBrowserRouter(routes)` in `src/main.tsx` and `RouterProvider` from `react-router/dom` in `App`. No Framework mode and no Declarative mode [N1]. Everything else is imported from `react-router`; `react-router-dom` is gone in v8 [N12].
- The router is created once at module level, never in a component or in state [N3].
- `src/routes.tsx` is the one route table. The areas (share-link views, organizer, admin) load with the route's `lazy` property, one chunk per area rather than per screen, since each chunk is a request that can fail on a weak connection [N4].
- Once a route is lazy, the root route defines `HydrateFallback` and `ErrorBoundary` [N5]. Each area has its own `ErrorBoundary`, which reads `useRouteError()` and tells an `ApiError` apart.
- Error boundaries are for unexpected failures; 422 messages and 409 reloads stay inside the screen [N6].
- The last child route, `path: "*"`, renders `NotFoundPage`, because Caddy answers every unknown path with `index.html` [N7].
- Organizer and admin routes are guarded by one client `middleware` on their parent route, which redirects to the login without a session; a test covers a logged-out deep link [N8].
- Paths are constants, and links are built with `generatePath`, never by joining strings [N9].
- An overlay, a sheet or dialog over a screen (Figma 6c, 6d, 7, 7b), is a nested route of that screen: the parent renders `<Outlet />`, and the overlay's page renders `ResponsiveSheet` (`src/components/ResponsiveSheet.tsx`), a bottom sheet on a phone, a centred dialog from `md` and a non-modal side panel from `lg`, which goes to the parent route when it closes. A link or a reload opens the overlay over its screen.
- Inside a tournament and its setup, `TournamentLayout` shows the tournament's header with its tabs, and on a phone the league's header and bottom bar step aside; the layout route says so through its `handle` (`src/lib/routeHandle.ts`). The tournament's own path redirects to the screen for its state, phase and format (`tournamentHome` in `src/features/tournaments/tournamentViews.ts`).
- `useParams()` types every parameter `string | undefined`; each area narrows them once, in a helper [N10].

## 10. Tests

### 10.1 Vitest

Checked by tools: ESLint Testing Library `flat/react` (among them `prefer-screen-queries`, `no-container`, `no-node-access`, `prefer-find-by`, `prefer-presence-queries`, `await-async-events`), `testing-library/prefer-user-event` and `testing-library/prefer-user-event-setup` [V11], `no-restricted-syntax` (`vi.mock` or `vi.doMock` of a module under `api/` [V6]), `@typescript-eslint/no-floating-promises`; Vitest 5 fails an assertion that is not awaited.

- Unit and component tests run in Vitest with jsdom (ADR-012); real browsers are Playwright's [V1]. A test sits next to its code as `*.test.ts` or `*.test.tsx`; `vite.config.ts` keeps `e2e/` out.
- `globals` stays off: tests import `describe`, `it` and `expect` from `vitest`, and `src/test/setup.ts` runs `cleanup()` and clears `localStorage` after each test [V2]. `restoreMocks` and `unstubGlobals` are on [V3].
- Elements are found by role first, then by label, then by text; `getByTestId` only when nothing else works. Finding an element by role also proves that it has a role and a name [V12].
- A test that needs the app renders `App` with `createMemoryRouter(routes)` and a fresh `QueryClient` with `retry: false`, as `renderAt` in `src/test/renderApp.tsx` does [V5].
- The API is mocked at the network with MSW's `setupServer` from `msw/node` and `onUnhandledFrame: "error"`, never by mocking the client module [V6] [V7]. `src/test/server.ts` serves the demo's handlers (`src/demo/handlers/`), so tests and the demo share one fake API; a test overrides them with `server.use()`. The handlers are typed through `route()` in `src/demo/route.ts`. A test that checks the client itself passes its own `fetch` to `createApi`, as `src/api/client.test.ts` does.

### 10.2 Playwright

Checked by tools: ESLint Playwright `flat/recommended` (among them `missing-playwright-await`, `prefer-web-first-assertions`, `no-wait-for-timeout`, `no-networkidle`, `no-force-option`, `no-focused-test`), `playwright/no-raw-locators` (except `html`) and `playwright/prefer-native-locators`; `forbidOnly` in `e2e/playwright.config.ts`.

- Tests run against the production images (ADR-013). Each test creates its own data through the API, in a fixture, and never depends on another test [V8].
- Each worker logs in with its own account. A saved `storageState` is never shared: presenting a rotated refresh cookie again revokes its family (ADR-006) [V9].
- `locale` is pinned to `en-US`. The language scenario switches with `test.use({ locale: "cs-CZ" })` instead of a second project, which would double the minutes (ADR-012) [V10].
- The accessibility checks are in §6.

## 11. Project structure

```text
frontend/
├── package.json, pnpm-lock.yaml, pnpm-workspace.yaml, .nvmrc
├── eslint.config.js, .prettierrc.json, tsconfig*.json, vite.config.ts, components.json
├── index.html
├── src/
│   ├── main.tsx          # entry: i18n, CSS, router, QueryClient, StrictMode
│   ├── App.tsx           # the providers around the router
│   ├── routes.tsx        # the one route table (§9)
│   ├── index.css         # Tailwind entry and theme tokens (§5)
│   ├── api/              # client.ts: api, dataOf, ApiError; schema.d.ts, generated
│   ├── i18n/             # set-up, language.ts (pickLanguage), locales/en.ts and cs.ts
│   ├── components/       # shared components; ui/ holds the shadcn/ui copies
│   ├── hooks/            # shared hooks, and those the shadcn CLI writes
│   ├── lib/              # utils.ts (cn)
│   ├── pages/            # screens outside any feature: home, not found
│   ├── features/<area>/  # api.ts, its components and screens
│   ├── demo/             # demo mode: the fake API, its contract and rules.ts (src/demo/README.md)
│   └── test/             # setup.ts, the MSW server and test helpers
└── e2e/                  # Playwright: configuration, specs, own tsconfig.json
```

Checked by tools: ESLint `no-restricted-imports` (imports flow one way: `api`, `i18n`, `components`, `hooks` and `lib` → `features` → `pages`, `routes.tsx`, `App.tsx` and `main.tsx`), `no-restricted-syntax` (`export * from` and `export { … } from`: no barrel files [S2]).

- The first real feature creates `src/features/<area>/`, with its `api.ts`, components and screens; the skeleton's other folders stay as they are [S1]. Features may import each other, since leagues, tournaments and matches are one domain.
- `@/` is the one import alias, for `src/`: `paths` without `baseUrl` in `tsconfig.app.json` [T3], `resolve.alias` in `vite.config.ts`.
- No barrel files (an `index.ts` that only re-exports): import each module directly [S2].
- Only `VITE_` environment variables reach the browser, and none holds a secret. The first one adds `src/vite-env.d.ts` with a typed `ImportMetaEnv` [S3].

Still to come with the first screens that need them:
- The 44 px Button size on the result-entry screen (§6).
- The Czech plural type for `cs` (§7).
- The `middleware` that guards organizer routes, with the login (§9).

Demo mode (`pnpm dev:demo`, `src/demo/README.md`) runs every screen against an MSW worker. MSW is a dev dependency; `main.tsx` loads the demo behind a `MODE !== "production"` check that the bundler removes, ESLint lets app code import only `@/demo/rules` and `@/demo/contract`, and Vite's MSW plugin, which serves the worker script, is on only in demo mode. CI fails the frontend job if any text file in `dist` matches `msw|setupWorker|mockServiceWorker`. Provisional API types live in `src/demo/contract.ts` until the backend's routes are generated into `schema.d.ts`; screens call those routes through `provisionalApi` (`src/api/provisional.ts`). Texts are split per area into `src/i18n/locales/{en,cs}/<area>.ts`, merged into the one namespace. The build puts each `src/features/<area>/` into one chunk.

## 12. Proposed changes to other documents

No change is proposed at the moment.

## 13. Sources

Each source with one sentence or phrase from it, checked on 2026-11-10.

**TypeScript**
- [T1] https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/ — "While TypeScript 7.0 is here, it does not ship with an API."
- [T2] https://typescript-eslint.io/users/dependency-versions — "The version range of TypeScript currently supported is `>=4.8.4 <6.1.0`."
- [T3] https://devblogs.microsoft.com/typescript/announcing-typescript-6-0/ — "`baseUrl` is deprecated and will no longer be considered a look-up root for module resolution."
- [T4] https://github.com/shadcn-ui/ui/issues/12493 — "Several generated components fail to type-check when the consuming project enables exactOptionalPropertyTypes."
- [T5] https://typescript-eslint.io/rules/no-import-type-side-effects/ — "in certain cases TS can leave behind a "side effect" import at runtime"
- [T6] https://www.typescriptlang.org/docs/handbook/release-notes/typescript-4-9.html — "The new `satisfies` operator lets us validate that the type of an expression matches some type, without changing the resulting type of that expression."
- [T7] https://typescript-eslint.io/rules/no-unused-vars/ — "We generally recommend using @typescript-eslint/no-unused-vars to flag unused locals and parameters instead of TypeScript."
- [T8] https://openapi-ts.dev/cli — `--enum`: "Generate true TS enums rather than string unions."
- [T9] https://www.typescriptlang.org/docs/handbook/enums.html — "In modern TypeScript, you may not need an enum when an object with `as const` could suffice"
- [T10] https://github.com/vitejs/vite/blob/main/packages/create-vite/template-react-ts/tsconfig.app.json — `"verbatimModuleSyntax": true`, `"erasableSyntaxOnly": true`, and no `strict`

**React**
- [R1] https://react.dev/reference/rules — "We strongly recommend using Strict Mode alongside React's ESLint plugin"
- [R2] https://react.dev/reference/react/forwardRef — "In React 19, `forwardRef` is no longer necessary."
- [R3] https://tanstack.com/query/latest/docs/framework/react/guides/does-this-replace-client-state — "TanStack Query is a server-state library, responsible for managing asynchronous operations between your server and client"
- [R4] https://react.dev/learn/passing-data-deeply-with-context — "Just because you need to pass some props several levels deep doesn't mean you should put that information into context."
- [R5] https://react.dev/blog/2025/10/01/react-19-2 — "Effect Events should _not_ be declared in the dependency array."
- [R6] https://react.dev/reference/react/use — "Promises passed to `use` must be cached so the same Promise instance is reused across re-renders."
- [R7] https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates — "This is the simpler variant, as it doesn't interact with the cache directly."
- [R8] https://ui.shadcn.com/docs/components/dropdown-menu — imports from "@/components/ui/dropdown-menu"
- [R9] https://react.dev/reference/eslint-plugin-react-hooks — "These rules are included in the `recommended` preset in `eslint-plugin-react-hooks`"
- [R10] https://github.com/ArnaudBarre/eslint-plugin-react-refresh — the vite config "enables the `allowConstantExport` and `allowCompoundComponents` options which are supported by Vite React plugins."

**Tooling**
- [E1] https://typescript-eslint.io/rules/no-misused-promises/ — "Whether to warn when a Promise is returned from a function typed as returning `void`."
- [E2] https://typescript-eslint.io/users/configs — "This configuration is not considered "stable" under Semantic Versioning (semver)."
- [E3] https://eslint.org/docs/latest/use/configure/rules — "Configuration comments can include descriptions to explain why the comment is necessary."
- [E4] https://prettier.io/docs/install — "Even a patch release of Prettier can result in slightly different formatting"
- [E5] https://prettier.io/docs/option-philosophy — "Option requests aren't accepted anymore."
- [E6] https://prettier.io/docs/integrating-with-linters — "These are **generally not recommended,** but can be useful in certain circumstances."
- [E7] https://github.com/tailwindlabs/prettier-plugin-tailwindcss — "`prettier-plugin-tailwindcss` _must_ be loaded last."
- [E8] https://github.com/prettier/prettier/blob/main/docs/cli.md — "By default, Prettier looks for `./.gitignore` and `./.prettierignore`."
- [E9] https://github.com/eslint-community/eslint-plugin-jsx-a11y-x — "There are two shareable configs, provided by the plugin."
- [E10] https://github.com/jsx-eslint/eslint-plugin-jsx-a11y/issues/1075 — the maintainer, on 2026-08-18: "Of course I intend to support it"
- [E11] https://github.com/pnpm/pnpm/releases/tag/v11.0.0 — "`minimumReleaseAge` defaults to 1 day (newly published packages are not resolved for 24h) and `blockExoticSubdeps` defaults to `true`."
- [E12] https://pnpm.io/settings/build — "A map of package matchers to explicitly allow (`true`) or disallow (`false`) script execution."
- [E13] https://pnpm.io/settings/cli#enginestrict — "installation fails when the project or a dependency declares an `engines.node` range that does not accept the current Node.js version"
- [E14] https://github.com/vitest-dev/vitest/releases/tag/v5.0.0 — "Write json and junit reporter output files to `.vitest` by default"
- [E15] https://vite.dev/blog/announcing-vite8 — "Babel is no longer a dependency and the installation size is smaller."
- [E16] https://github.com/tailwindlabs/tailwindcss.com/blob/main/src/docs/compatibility.mdx — "Tailwind CSS v4.0 is designed for and tested on modern browsers"; minimums Chrome 111, Safari 16.4, Firefox 128
- [E17] https://github.com/vitejs/vite/blob/main/docs/guide/build.md — the default target: "Chrome >=111 … Firefox >=114 … Safari >=16.4"
- [E18] https://github.com/pnpm/pnpm.io/blob/main/docs/cli/audit.md — "Checks for known security issues with the installed packages."
- [E19] https://github.com/pnpm/pnpm/releases/tag/v12.0.0 — "it fails the command with `ERR_PNPM_UNRECOGNIZED_WORKSPACE_SETTINGS` when the project pins a pnpm version the running pnpm satisfies"

**ESLint 10 support of the plugins** (peer ranges in the lockfile, checked on 2026-11-10): every plugin names ESLint 10 except two, whose ranges are open-ended.
- `eslint-plugin-playwright`: peer `>=8.40.0`; its repository develops against `eslint ^10.0.0`.
- `eslint-plugin-simple-import-sort`: peer `>=5.0.0`; https://github.com/lydell/eslint-plugin-simple-import-sort/issues/205, the maintainer — "I did a quick test and the plugin seems to work with ESLint 10."

**Tailwind and shadcn/ui**
- [W1] https://tailwindcss.com/docs/compatibility — "is not designed to be used with CSS preprocessors like Sass, Less, or Stylus."
- [W2] https://tailwindcss.com/docs/theme — "Use `@theme` when you want a design token to map directly to a utility class, and use `:root` for defining regular CSS variables that shouldn't have corresponding utility classes."
- [W3] https://tailwindcss.com/docs/theme — "all of the default utilities that use that namespace _(like `bg-red-500`)_ will be removed"
- [W4] https://developer.mozilla.org/en-US/docs/Web/CSS/color-scheme — the `<meta name="color-scheme">` goes "before any CSS style information … helping prevent unwanted screen flashes during the page load."
- [W5] https://tailwindcss.com/docs/responsive-design — "Don't think of `sm:` as meaning "on small screens""
- [W6] https://tailwindcss.com/docs/responsive-design — "Just like breakpoint variants, container queries are mobile-first in Tailwind CSS and apply at the target container size and up."
- [W7] https://tailwindcss.com/docs/adding-custom-styles — "once in a while you need to break out of those constraints to get things pixel-perfect"
- [W8] https://tailwindcss.com/docs/styling-with-utility-classes — "Inline styles are still very useful … particularly when a value is coming from a dynamic source like a database or API"
- [W9] https://tailwindcss.com/docs/styling-with-utility-classes — "exposing specific props for styling customizations instead of letting consumers add extra classes"
- [W10] https://tailwindcss.com/docs/styling-with-utility-classes — "If you need to reuse some styles across multiple files, the best strategy is to create a _component_"
- [W11] https://tailwindcss.com/docs/functions-and-directives — "This function is deprecated, and we recommend using CSS theme variables instead."
- [W12] https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default — "New projects default to Base UI."
- [W13] https://ui.shadcn.com/docs/components-json — "This cannot be changed after initialization."
- [W14] https://ui.shadcn.com/docs/theming — "We use semantic background and foreground pairs."
- [W15] https://ui.shadcn.com/docs/changelog/2026-09-cn — "`cn` is a drop-in replacement for `twMerge(clsx(...))`."
- [W16] https://ui.shadcn.com/docs/changelog/2026-05-shadcn-eject — "It inlines `shadcn/tailwind.css` into your global CSS file and removes the `shadcn` dependency"
- [W17] https://ui.shadcn.com/docs — "This is not a component library. It is how you build your component library."
- [W18] https://ui.shadcn.com/docs/cli — `-o, --overwrite`: "overwrite existing files. (default: false)"
- [W19] https://ui.shadcn.com/docs/changelog/2026-04-shadcn-apply — "We added `shadcn apply` so you can switch presets in an existing project without starting over."
- [W20] https://tailwindcss.com/docs/outline-style — "Use the `outline-hidden` utility to hide the default browser outline on focused elements, while still preserving the outline in forced colors mode"
- [W21] https://tailwindcss.com/docs/dark-mode — "By default this uses the `prefers-color-scheme` CSS media feature"
- [W22] https://github.com/schoero/eslint-plugin-better-tailwindcss — "Report classes not registered with Tailwind CSS."

**Accessibility**
- [A1] https://www.w3.org/TR/WCAG22/ — "W3C Recommendation 12 December 2024"
- [A2] https://www.w3.org/TR/WCAG22/ — 2.5.5 (Level AAA): "The size of the target for pointer inputs is at least 44 by 44 CSS pixels except when:"
- [A3] https://www.w3.org/TR/WCAG22/ — 1.4.3: "a contrast ratio of at least 4.5:1"
- [A4] https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html — "the visual focus indicator for a component must have sufficient contrast against the adjacent background"
- [A5] https://www.w3.org/TR/WCAG22/ — 2.4.11: "When a user interface component receives keyboard focus, the component is not entirely hidden due to author-created content."
- [A6] https://www.w3.org/WAI/WCAG22/Techniques/css/C39 — "allow users to prevent animations (including motion animations) from being displayed on web pages"
- [A7] https://react.dev/reference/react-dom/components/title — "Only render a single `<title>` at a time."
- [A8] https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA21 — "The error message is associated with the field using `aria-describedby`"
- [A9] https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html — "ARIA22: Using role=status to present status messages"
- [A10] https://www.w3.org/WAI/WCAG22/Techniques/html/H101 — "It is a suggested approach to include all content on the page in landmarks."
- [A11] https://www.w3.org/WAI/WCAG22/Understanding/language-of-parts.html — "except for proper names, technical terms, words of indeterminate language, and words or phrases"
- [A12] https://www.w3.org/TR/WCAG22/ — 2.5.7: "All functionality that uses a dragging movement for operation can be achieved by a single pointer without dragging,"
- [A13] https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html — "Copy and paste can be relied on to avoid transcription."
- [A14] https://github.com/mdn/content/blob/main/files/en-us/web/html/reference/global_attributes/inputmode/index.md — `numeric`: "Numeric input keyboard, but only requires the digits 0–9."
- [A15] https://www.w3.org/WAI/WCAG22/Understanding/reflow.html — "Vertical scrolling content at a width equivalent to 320 CSS pixels;"
- [A16] https://playwright.dev/docs/accessibility-testing — "Test fixtures are a good way to share common AxeBuilder configuration across many tests."
- [A17] https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md — "These rules are disabled by default, until WCAG 2.2 is more widely adopted and required."
- [A19] https://www.w3.org/TR/WCAG22/ — 2.5.8 (Level AA): "The size of the target for pointer inputs is at least 24 by 24 CSS pixels, except when:"
- [A20] https://developer.mozilla.org/en-US/docs/Web/CSS/env — "to ensure that fixed app toolbar buttons are not obscured by device notifications appearing at the bottom of the screen"
- [A21] https://css-tricks.com/16px-or-larger-text-prevents-ios-form-zoom/ — "If the font-size of an <input> is 16px or larger, Safari on iOS will focus into the input"
- [A22] https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/meta/name/theme-color — "To set the media to which the theme color metadata applies, include the `media` attribute"
- [A18] https://github.com/dequelabs/axe-core — "With axe-core, you can find on average 57% of WCAG issues automatically."

**Translations**
- [I1] https://github.com/i18next/i18next-cli — the linter reports "user-facing text in JSX elements and attributes that isn't wrapped in `t()`/`<Trans>`."
- [I2] https://www.i18next.com/overview/typescript — `resources`: "This is the most important option that is used to infer the appropriate keys and return types."
- [I3] https://react.i18next.com/latest/i18next-instance — "React escapes what it renders"
- [I4] https://react.i18next.com/latest/trans-component — "most projects find the named-components form the easiest to read and maintain"
- [I5] https://www.i18next.com/translation-function/plurals — "Note: The variable name must be `count`."
- [I6] https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html — Czech cardinals: one "1 den", few "2 dny", many "1,5 dne", other "5 dní"; ordinals: other only
- [I7] https://www.i18next.com/translation-function/formatting — "you can use the built-in formatting functions based on the Intl API."
- [I8] https://www.i18next.com/overview/configuration-options — `fallbackLng`: "Without it (`false`, the default since v27) no fallback language is loaded"

**Data**
- [Q1] https://tanstack.com/query/latest/docs/eslint/prefer-query-options — wrapping queries in `queryOptions` "co-locates the key and function, making queries safer and easier to reuse"
- [Q2] https://tanstack.com/query/latest/docs/framework/react/guides/query-invalidation — "Invalidate every query with a key that starts with `todos`"
- [Q3] https://tanstack.com/query/latest/docs/framework/react/guides/query-functions — "the query function **must throw** or return a **rejected Promise**"
- [Q4] https://tanstack.com/query/latest/docs/framework/react/typescript — "set a global Error type for everything, without having to specify generics on call-sides"
- [Q5] https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation — "When a query becomes out-of-date or inactive, this `signal` will become aborted."
- [Q6] https://tanstack.com/query/latest/docs/framework/react/guides/query-retries — "Setting `retry = (failureCount, error) => ...` allows for custom logic based on why the request failed."
- [Q7] https://github.com/TanStack/query/blob/main/docs/framework/react/guides/important-defaults.md — "Setting staleTime is the recommended way to avoid excessive refetches"
- [Q8] https://tanstack.com/query/latest/docs/framework/react/guides/invalidations-from-mutations — "Returning a Promise on `onSuccess` makes sure the data is updated before the mutation is entirely complete"
- [Q9] https://tanstack.com/query/latest/docs/framework/react/guides/mutations — "All mutations with the same `scope.id` will run in serial"
- [Q10] https://tanstack.com/query/latest/docs/framework/react/guides/network-mode — "Queries can be in `state: 'pending'`, but `fetchStatus: 'paused'` if they are mounting for the first time, and you have no network connection."
- [Q11] https://tanstack.com/query/latest/docs/framework/react/guides/suspense — "with suspense, all your Queries inside one component are fetched in serial."
- [Q12] https://tanstack.com/query/latest/docs/framework/react/reference/functions/useQuery — `throwOnError`: "If set to `true` or `suspense` is `true`, all errors will be thrown to the error boundary."
- [Q13] https://tanstack.com/query/latest/docs/framework/react/reference/interfaces/MutationCacheConfig — "Global callbacks that fire for every mutation handled by a `MutationCache`, regardless of which component or observer triggered it."
- [Q14] https://tanstack.com/query/latest/docs/framework/react/guides/mutations — "those additional callbacks won't run if your component unmounts _before_ the mutation finishes."
- [Q15] https://github.com/openapi-ts/openapi-typescript/blob/main/packages/openapi-react-query/src/index.ts — `queryKey: [method, path, init],`
- [Q16] https://openapi-ts.dev/openapi-fetch/ — `error`: "5xx, 4xx, or `default` response if not OK; otherwise `undefined`"
- [Q17] https://developer.mozilla.org/en-US/docs/Web/API/Request/clone — "`clone()` throws a `TypeError` if the request body has already been used."
- [Q18] https://openapi-ts.dev/openapi-fetch/middleware-auth — "the access token is kept in JavaScript module state, which is safe to do for client applications"
- [Q19] https://openapi-ts.dev/openapi-react-query/ — "Also eliminates `as` type overrides that can also hide bugs"

**Routing**
- [N1] https://reactrouter.com/start/modes — "Use Data Mode if you: … want data features but also want to have control over bundling, data, and server abstractions"
- [N2] https://github.com/remix-run/react-router/blob/main/packages/react-router/CHANGELOG.md — "`RouterProvider`/`HydratedRouter` should be imported from `react-router/dom`"
- [N3] https://reactrouter.com/start/data/installation — "Data Routers should not be held in React state."
- [N4] https://reactrouter.com/start/data/custom — "Routes can take most of their definition lazily with the `lazy` property."
- [N5] https://github.com/remix-run/react-router/blob/main/packages/react-router/lib/hooks.tsx — "No `HydrateFallback` element provided to render during initial hydration"
- [N6] https://reactrouter.com/how-to/error-boundary — "Error boundaries are not intended for rendering form validation errors or error reporting."
- [N7] https://reactrouter.com/how-to/spa — "you'll need to configure your host to direct all URLs to the `index.html` of the client build"
- [N8] https://reactrouter.com/how-to/middleware — "Client middlewares will run on every client navigation, regardless of whether there are `loader`s to run."
- [N9] https://reactrouter.com/api/utils/generatePath — "Returns a path with params interpolated."
- [N10] https://reactrouter.com/api/hooks/useParams — params typed `Record<string, string | undefined>`
- [N12] https://github.com/remix-run/react-router/blob/main/packages/react-router/CHANGELOG.md — v8.0.0: "Remove `react-router-dom` package"
- [N11] https://reactrouter.com/explanation/state-management — loaders, actions and forms come "with automatic synchronization through revalidation", a second cache next to TanStack Query

**Tests**
- [V1] https://vitest.dev/guide/browser/why — "these tools only simulate a browser environment and not an actual browser"
- [V2] https://vitest.dev/config/globals — "some libraries, e.g., `@testing-library/react`, rely on globals being present to perform auto cleanup."
- [V3] https://vitest.dev/config/restoremocks — "This restores all original implementations on spies created manually with `vi.spyOn`."
- [V4] https://vitest.dev/config/ — "Create `vitest.config.ts`, which will have the higher priority and will **override** the configuration from `vite.config.ts`"
- [V5] https://tanstack.com/query/latest/docs/framework/react/guides/testing — "This will set the defaults for all queries in the component tree to "no retries"."
- [V6] https://openapi-ts.dev/openapi-fetch/testing — "Mock Service Worker … is highly recommended for mocking API responses in tests"
- [V7] https://github.com/mswjs/msw/releases/tag/v3.0.0 — "`onUnhandledRequest` option has been renamed to `onUnhandledFrame`."
- [V8] https://playwright.dev/docs/best-practices — "Each test should be completely isolated from another test and should run independently."
- [V9] https://playwright.dev/docs/auth — one account per parallel worker: "This is the recommended approach for tests that modify server-side state."
- [V10] https://playwright.dev/docs/emulation — "Emulate the browser Locale and Timezone which can be set globally for all tests in the config"
- [V11] https://testing-library.com/docs/user-event/intro — "We recommend invoking `userEvent.setup()` before the component is rendered."
- [V12] https://testing-library.com/docs/queries/about/ — `getByRole`: "This should be your top preference for just about everything."

**Structure**
- [S1] https://legacy.reactjs.org/docs/faq-structure.html — "locate CSS, JS, and tests together inside folders grouped by feature or route" (legacy documentation)
- [S2] https://vite.dev/guide/performance — "If possible, you should avoid barrel files and import the individual APIs directly"
- [S3] https://vite.dev/guide/env-and-mode — "`VITE_*` variables should _not_ contain sensitive information such as API keys."
