import { defineConfig } from "i18next-cli";

// Only `lint` runs: it reports user-facing text outside t() and <Trans>
// (ADR-003). The texts are TypeScript objects (src/i18n/locales), so
// there are no translation files for the other commands to write.
export default defineConfig({
  locales: ["en", "cs"],
  extract: {
    input: ["src/**/*.{ts,tsx}"],
    ignore: ["src/**/*.test.{ts,tsx}", "src/api/schema.d.ts"],
    output: "src/i18n/locales/{{language}}.json",
  },
});
