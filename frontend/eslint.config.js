// @ts-check
// The lint rules of docs/style/frontend-style.md. The guide names each rule by its
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
  // Packages the project decided against (guide §4, §7, §8.2, §9).
  ...[
    ["react-router-dom", "frontend-style §9: import from react-router."],
    ["axios", "frontend-style §8.2: call the API through src/api/."],
    [
      "openapi-react-query",
      "frontend-style §8.2: its keys cannot be invalidated by a league's prefix.",
    ],
    ["react-hook-form", "frontend-style §4: forms use no form library."],
    ["zod", "frontend-style §4: the server validates; no client schema."],
    [
      "i18next-browser-languagedetector",
      "frontend-style §7: the language comes from pickLanguage.",
    ],
  ].map(([name, message]) => ({ name, message })),
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
// src/test holds the tests' helpers and the fake API (src/test/fake); app
// code never imports it, so no test code reaches a production bundle.
const testInternals = {
  regex: "^(@/|(\\.\\./)+)test(/|$)",
  message:
    "App code imports nothing from src/test; the fake API and the test helpers are for tests.",
};
// The files directly in src/ (main.tsx, App.tsx, routes.tsx) are the app's
// entry; testInternals above matches "../test" and "@/test", this matches the
// "./test" they would write.
const testFromRoot = {
  regex: "^\\./test(/|$)",
  message:
    "App code imports nothing from src/test; the fake API and the test helpers are for tests.",
};
// A dynamic import() is not an import declaration, so the import patterns
// miss it. esquery has no escaped "/" in a regex, hence \x2F.
const testImportSyntax = [
  {
    selector: "ImportExpression[source.value=/^(\\.|@)\\x2Ftest(\\x2F|$)/]",
    message:
      "App code imports nothing from src/test; the fake API and the test helpers are for tests.",
  },
];
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

// Selectors of no-restricted-syntax beyond forwardRef. A block that sets the
// rule replaces its whole list, so each block names every group it keeps.
// esquery has no escaped "/" in a regex, hence \x2F.
const optimisticSyntax = [
  "ImportSpecifier[imported.name='useOptimistic']",
  "MemberExpression[property.name='useOptimistic']",
  "MemberExpression[property.name=/^set(Query|Queries)Data$/]",
  "Property[key.name='onMutate']",
].map((selector) => ({
  selector,
  message:
    "frontend-style §8.1: no optimistic cache writes; render mutation.variables while pending.",
}));
const pathSyntax = [
  "TemplateLiteral[quasis.0.value.raw=/^\\x2F/]",
  "BinaryExpression[operator='+'] > Literal[value=/^\\x2F/]",
].map((selector) => ({
  selector,
  message:
    "frontend-style §9: build paths with generatePath and the constants in @/lib/paths.",
}));
// esquery reads a missing attribute as the text "undefined", so the selector
// for `undefined` also asks for an Identifier.
const intlSyntax = ["NewExpression", "CallExpression"].flatMap((call) =>
  [
    ":not([arguments.0])",
    "[arguments.0.type='Literal']",
    "[arguments.0.type='Identifier'][arguments.0.name='undefined']",
  ].map((argument) => ({
    selector: `${call}[callee.object.name='Intl']${argument}`,
    message: "frontend-style §7: pass i18n.resolvedLanguage as the locale.",
  })),
);
const barrelSyntax = [
  "ExportAllDeclaration",
  "ExportNamedDeclaration[source]",
].map((selector) => ({
  selector,
  message: "frontend-style §11: no barrel files; import each module directly.",
}));
const htmlSyntax = [
  {
    selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
    message: "frontend-style §7: render text as React children, never as HTML.",
  },
];
// `as const` stays; a CSS custom property is not in CSSProperties (§5.1),
// written bare or as React.CSSProperties.
const assertionSyntax = [
  "TSAsExpression:not([typeAnnotation.typeName.name=/^(const|CSSProperties)$/]):not([typeAnnotation.typeName.right.name='CSSProperties'])",
  "TSTypeAssertion",
].map((selector) => ({
  selector,
  message:
    "frontend-style §8.2: no `as` on API data; types come from the generated schema. Any other `as` gets a disable comment that says why it is safe (§3).",
}));
const queryClientSyntax = [
  {
    selector: "NewExpression[callee.name='QueryClient']",
    message:
      "frontend-style §8.1: the one QueryClient is created in src/main.tsx.",
  },
];
const routerDataSyntax = [
  {
    selector: "Property[key.name=/^(loader|action|shouldRevalidate)$/]",
    message:
      "frontend-style §9: API data goes through TanStack Query, not router loaders or actions.",
  },
];
// The module is named by a string or, in Vitest's typed form, by import("…").
const mockApiSyntax = ["value", "source.value"].map((specifier) => ({
  selector: `CallExpression[callee.object.name='vi'][callee.property.name=/^(mock|doMock)$/][arguments.0.${specifier}=/(^|\\x2F)api(\\x2F|$)/]`,
  message:
    "frontend-style §10.1: mock the network with MSW, never the API modules.",
}));
const mutationSyntax = [
  {
    selector:
      "CallExpression[callee.name='mutationOptions'] > ObjectExpression > Property[key.name='onSuccess']",
    message:
      "frontend-style §8.1: cache work after a mutation goes in onSettled. A real exception gets an eslint-disable-next-line with its reason.",
  },
];
const appSyntax = [
  ...forwardRefSyntax,
  ...optimisticSyntax,
  ...pathSyntax,
  ...intlSyntax,
  ...barrelSyntax,
  ...htmlSyntax,
];

// One cn for the whole app, configured with the theme's text styles; the
// package alone takes text-caption for a colour (guide §5.3).
const cnPackage = {
  group: ["cn", "cn/*"],
  message: "Import cn from @/lib/utils, which knows the theme's text styles.",
};

/** @param {object[]} patterns */
function restrictImports(...patterns) {
  return /** @type {const} */ ([
    "error",
    {
      paths: restrictedPaths,
      patterns: [unstableRouterApis, cnPackage, ...patterns],
    },
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
  {
    pattern: "(^|:)(ring|outline)-ring/",
    message:
      "frontend-style §5.2: the focus ring is solid, so it keeps 3:1 next to the primary colour.",
  },
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
      "no-restricted-syntax": [
        "error",
        ...appSyntax,
        ...assertionSyntax,
        ...queryClientSyntax,
      ],
      // These use the browser's locale, not the chosen language.
      "no-restricted-properties": [
        "error",
        ...["toLocaleString", "toLocaleDateString", "toLocaleTimeString"].map(
          (property) => ({
            property,
            message: "Format with Intl in i18n.resolvedLanguage.",
          }),
        ),
        {
          property: "localeCompare",
          message:
            "Sort names with an Intl.Collator in i18n.resolvedLanguage; compare ISO dates as plain strings.",
        },
      ],
      "no-restricted-imports": restrictImports(apiClient, testInternals),
    },
  },
  {
    files: ["src/{components,hooks,i18n,lib}/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictImports(
        apiClient,
        appFromShared,
        testInternals,
      ),
    },
  },
  {
    // The one file that configures the cn package.
    files: ["src/lib/utils.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: restrictedPaths,
          patterns: [
            unstableRouterApis,
            apiClient,
            appFromShared,
            testInternals,
          ],
        },
      ],
    },
  },
  {
    files: ["src/features/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictImports(
        apiClient,
        appFromFeature,
        testInternals,
      ),
    },
  },
  {
    files: ["src/api/**/*.ts"],
    rules: {
      "no-restricted-globals": "off",
      "no-restricted-imports": restrictImports(appFromShared, testInternals),
    },
  },
  {
    files: ["src/features/*/api.ts"],
    rules: {
      "no-restricted-imports": restrictImports(appFromFeature, testInternals),
      "no-restricted-syntax": [
        "error",
        ...appSyntax,
        ...assertionSyntax,
        ...queryClientSyntax,
        ...mutationSyntax,
      ],
    },
  },
  {
    // Tests run against the fake API (src/test/server.ts, src/test/fake).
    files: ["src/test/**/*.{ts,tsx}", "src/**/*.test.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictImports(apiClient),
    },
  },
  {
    // These tests read what the fake API holds straight through `api`.
    files: [
      "src/features/fields/fields.test.tsx",
      "src/features/public/public.test.tsx",
      "src/features/tournaments/finals/finals.test.tsx",
    ],
    rules: { "no-restricted-imports": restrictImports() },
  },
  {
    // The fake API, its tests and its helper call the API through the clients.
    files: ["src/test/fake/**/*.ts", "src/test/setupTestHelpers.ts"],
    rules: { "no-restricted-imports": restrictImports() },
  },
  {
    // The files directly in src/ may not import src/test, static or dynamic;
    // their tests may. main.tsx and routes.tsx add the syntax rule below.
    files: ["src/*.{ts,tsx}"],
    ignores: ["src/*.test.{ts,tsx}"],
    rules: {
      "no-restricted-imports": restrictImports(
        apiClient,
        testInternals,
        testFromRoot,
      ),
      "no-restricted-syntax": [
        "error",
        ...appSyntax,
        ...assertionSyntax,
        ...queryClientSyntax,
        ...testImportSyntax,
      ],
    },
  },
  {
    files: ["src/routes.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        ...appSyntax,
        ...assertionSyntax,
        ...queryClientSyntax,
        ...routerDataSyntax,
        ...testImportSyntax,
      ],
    },
  },
  {
    files: ["src/main.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        ...appSyntax,
        ...assertionSyntax,
        ...testImportSyntax,
      ],
    },
  },
  {
    // Tests make their own QueryClient (renderAt in src/test/renderApp.tsx).
    files: ["src/test/**/*.{ts,tsx}", "src/**/*.test.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        ...appSyntax,
        ...assertionSyntax,
        ...mockApiSyntax,
      ],
    },
  },
  {
    // The fake engines are stand-ins that leave with the fake API; no `as`
    // rule there.
    files: ["src/test/fake/**/*.ts", "src/test/setupTestHelpers.ts"],
    ignores: ["src/test/fake/**/*.test.ts"],
    rules: {
      "no-restricted-syntax": ["error", ...appSyntax, ...queryClientSyntax],
    },
  },
  {
    // The fake API's tests: the tests' list without the `as` rule.
    files: ["src/test/fake/**/*.test.ts"],
    rules: {
      "no-restricted-syntax": ["error", ...appSyntax, ...mockApiSyntax],
    },
  },
  {
    files: ["src/**/*.tsx"],
    extends: [jsxA11yX.configs.strict],
    settings: {
      // Each copied component that renders a native control is listed here.
      "jsx-a11y-x": {
        components: {
          Button: "button",
          Input: "input",
          Textarea: "textarea",
          Label: "label",
        },
      },
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
