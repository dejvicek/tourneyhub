// @ts-check
// The lint rules of docs/frontend-style.md. The guide names each rule by its
// ID; a rule beyond the presets says here why it is on (guide §2).
import js from "@eslint/js";
import pluginQuery from "@tanstack/eslint-plugin-query";
import { defineConfig, globalIgnores } from "eslint/config";
import betterTailwindcss from "eslint-plugin-better-tailwindcss";
import jsxA11yX from "eslint-plugin-jsx-a11y-x";
import playwright from "eslint-plugin-playwright";
import reactHooks from "eslint-plugin-react-hooks";
import { reactRefresh } from "eslint-plugin-react-refresh";
import simpleImportSort from "eslint-plugin-simple-import-sort";
import testingLibrary from "eslint-plugin-testing-library";
import globals from "globals";
import tseslint from "typescript-eslint";

// Imports no file in src/ uses (guide §4, §8, §9). forwardRef is banned by
// forwardRefSyntax below: importNames would also flag `import * as React`,
// which the copied shadcn/ui components use.
const restrictedPaths = [
  {
    name: "@tanstack/react-query",
    importNames: [
      "useSuspenseQuery",
      "useSuspenseQueries",
      "useSuspenseInfiniteQuery",
    ],
    message: "Use useQuery and render the pending, paused and error states.",
  },
  {
    name: "react-router",
    importNames: [
      "Form",
      "useActionData",
      "useFetcher",
      "useFetchers",
      "useLoaderData",
      "useRouteLoaderData",
      "useSubmit",
    ],
    message: "API data goes through TanStack Query, not the router.",
  },
];
const unstableRouterApis = {
  group: ["react-router", "react-router/*"],
  importNamePattern: "^unstable_",
  message: "unstable_ APIs are not meant for production.",
};
// Components never see URLs or HTTP: they use the query and mutation options
// of the API modules (guide §8).
const apiClient = {
  regex: "(^|/)api/client$",
  importNames: ["api", "createApi", "dataOf"],
  message: "Only src/api/ and a feature's api.ts call the API.",
};
// Imports flow one way: shared code → features → the app (guide §11).
const appFromShared = {
  regex: "^(@/|(\\.\\./)+)(App|main|routes|pages|features)(/|$)",
  message: "Shared code does not import features, screens or the app.",
};
const appFromFeature = {
  regex: "^(@/|(\\.\\./)+)(App|main|routes|pages)(/|$)",
  message: "A feature does not import screens outside it or the app.",
};

const forwardRefMessage = "React 19 passes ref as an ordinary prop.";
const forwardRefSyntax = [
  {
    selector:
      "ImportDeclaration[source.value='react'] > ImportSpecifier[imported.name='forwardRef']",
    message: forwardRefMessage,
  },
  {
    selector:
      "MemberExpression[object.name='React'][property.name='forwardRef']",
    message: forwardRefMessage,
  },
];

/** @param {object[]} patterns */
function restrictImports(...patterns) {
  return /** @type {const} */ ([
    "error",
    { paths: restrictedPaths, patterns: [unstableRouterApis, ...patterns] },
  ]);
}

// Class names that bypass the theme or the mobile-first layout (guide §5).
const restrictedClasses = [
  {
    pattern: "^(.*:)?outline-none$",
    fix: "$1outline-hidden",
    message: "outline-hidden keeps the outline in forced colours mode.",
  },
  {
    pattern: "(^|:)@?max-[^:]*:",
    message: "Mobile-first: add larger layouts with min-width variants.",
  },
  {
    pattern: "(^|:)@?min-\\[[^:]*:",
    message: "Breakpoints come from the theme.",
  },
  { pattern: "(^!|:!|!$)", message: "No important modifier." },
];
const restrictedClassesOutsideUi = [
  ...restrictedClasses,
  {
    pattern: "(^|:)dark:",
    message:
      "Theme tokens switch with the theme; dark: is for src/components/ui only.",
  },
  {
    pattern:
      "-\\[(#|color:|(rgba?|hsla?|oklch|oklab|lch|lab|color|color-mix|light-dark)\\()",
    message: "Colours come from theme tokens.",
  },
  {
    pattern: "\\[(background-|border-)?color:",
    message: "Colours come from theme tokens.",
  },
  {
    pattern:
      "(^|:)(bg|text|border(-[trblxyse])?|ring|outline|fill|stroke|from|via|to|accent|caret|decoration|divide|shadow)-\\[[a-zA-Z]+\\]",
    message: "Colours come from theme tokens, not named colours.",
  },
  {
    pattern: "(^|:)[a-z-]+-(black|white)(/|$)",
    message:
      "Colours come from theme tokens; black and white are for src/components/ui only.",
  },
];

export default defineConfig([
  globalIgnores([
    "dist",
    "coverage",
    "src/api/schema.d.ts",
    "e2e/test-results",
    "e2e/playwright-report",
  ]),
  {
    linterOptions: {
      reportUnusedDisableDirectives: "error",
      reportUnusedInlineConfigs: "error",
    },
  },
  {
    files: ["**/*.{js,ts,tsx}"],
    plugins: { "simple-import-sort": simpleImportSort },
    rules: {
      "simple-import-sort/imports": "error",
      "simple-import-sort/exports": "error",
    },
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // A new member of a union, such as a new error code in openapi.json,
      // fails lint wherever a switch does not handle it.
      "@typescript-eslint/switch-exhaustiveness-check": [
        "error",
        {
          allowDefaultCaseForExhaustiveSwitch: false,
          requireDefaultForNonUnion: true,
        },
      ],
      // verbatimModuleSyntax keeps `import { type X }` as a side-effect
      // import; a type-only import is written `import type { X }`.
      "@typescript-eslint/no-import-type-side-effects": "error",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [pluginQuery.configs["flat/recommended-strict"]],
    rules: {
      "@tanstack/query/no-rest-destructuring": "error",
      // Requests go through the API client, which adds auth and turns
      // errors into ApiError (ADR-008).
      "no-restricted-globals": [
        "error",
        {
          globals: [
            { name: "fetch", message: "Call the API through src/api/." },
          ],
          checkGlobalObject: true,
        },
      ],
      "no-restricted-syntax": ["error", ...forwardRefSyntax],
      // These format in the browser's locale, not the chosen language.
      "no-restricted-properties": [
        "error",
        ...["toLocaleString", "toLocaleDateString", "toLocaleTimeString"].map(
          (property) => ({
            property,
            message: "Format with Intl in i18n.resolvedLanguage.",
          }),
        ),
      ],
      "no-restricted-imports": restrictImports(apiClient),
    },
  },
  {
    files: ["src/{components,hooks,i18n,lib}/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictImports(apiClient, appFromShared),
    },
  },
  {
    files: ["src/features/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictImports(apiClient, appFromFeature),
    },
  },
  {
    files: ["src/api/**/*.ts"],
    rules: {
      "no-restricted-globals": "off",
      "no-restricted-imports": restrictImports(appFromShared),
    },
  },
  {
    files: ["src/features/*/api.ts"],
    rules: { "no-restricted-imports": restrictImports(appFromFeature) },
  },
  {
    files: ["src/**/*.tsx"],
    extends: [jsxA11yX.configs.strict],
    settings: {
      // Each copied component that renders a native control is listed here.
      "jsx-a11y-x": { components: { Button: "button" } },
    },
    rules: {
      // Off in both of the plugin's configs; every control needs a name.
      "jsx-a11y-x/control-has-associated-label": [
        "error",
        jsxA11yX.configs.strict.rules?.[
          "jsx-a11y-x/control-has-associated-label"
        ]?.[1],
      ],
    },
  },
  {
    files: ["src/**/*.tsx"],
    // The shadcn/ui files also export their variants (buttonVariants).
    ignores: ["src/components/ui/**"],
    extends: [reactRefresh.configs.vite()],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "better-tailwindcss": betterTailwindcss },
    settings: {
      "better-tailwindcss": {
        entryPoint: "src/index.css",
        cwd: import.meta.dirname,
      },
    },
    rules: {
      // Class order and line wrapping are Prettier's (prettier-plugin-tailwindcss).
      "better-tailwindcss/no-unknown-classes": "error",
      "better-tailwindcss/no-conflicting-classes": "error",
      "better-tailwindcss/no-duplicate-classes": "error",
      "better-tailwindcss/no-deprecated-classes": "error",
      "better-tailwindcss/no-concatenated-classes": "error",
      "better-tailwindcss/enforce-consistent-variable-syntax": "error",
      "better-tailwindcss/no-restricted-classes": [
        "error",
        { restrict: restrictedClasses },
      ],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/components/ui/**"],
    rules: {
      "better-tailwindcss/no-restricted-classes": [
        "error",
        { restrict: restrictedClassesOutsideUi },
      ],
    },
  },
  {
    files: ["src/**/*.test.{ts,tsx}"],
    extends: [testingLibrary.configs["flat/react"]],
    rules: {
      // Neither is in a preset: tests act through user-event, set up first.
      "testing-library/prefer-user-event": "error",
      "testing-library/prefer-user-event-setup": "error",
    },
  },
  {
    files: ["e2e/**/*.ts"],
    extends: [playwright.configs["flat/recommended"]],
    rules: {
      // Neither is in the preset: tests locate by role, label or text.
      // `<html lang>` has no role to locate it by.
      "playwright/no-raw-locators": ["error", { allowed: ["html"] }],
      "playwright/prefer-native-locators": "error",
    },
  },
  {
    files: ["**/*.js"],
    extends: [js.configs.recommended],
    languageOptions: {
      globals: globals.node,
    },
  },
]);
