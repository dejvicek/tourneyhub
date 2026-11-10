import { describe, expect, it } from "vitest";

import { isDemoMode } from "./demoMode";

describe("isDemoMode", () => {
  it("is off in a production build, even with VITE_DEMO=true", () => {
    expect(isDemoMode({ MODE: "production" })).toBe(false);
    expect(isDemoMode({ MODE: "production", VITE_DEMO: "true" })).toBe(false);
  });

  it("is off in development and tests unless VITE_DEMO is true", () => {
    expect(isDemoMode({ MODE: "development" })).toBe(false);
    expect(isDemoMode({ MODE: "development", VITE_DEMO: "1" })).toBe(false);
    expect(isDemoMode({ MODE: "test", VITE_DEMO: "false" })).toBe(false);
  });

  it("is on with pnpm dev:demo or VITE_DEMO=true outside production", () => {
    expect(isDemoMode({ MODE: "demo", VITE_DEMO: "true" })).toBe(true);
    expect(isDemoMode({ MODE: "development", VITE_DEMO: "true" })).toBe(true);
  });

  it("is off in this test run", () => {
    expect(isDemoMode(import.meta.env)).toBe(false);
  });
});
