import { describe, expect, it } from "vitest";

import { pickLanguage } from "./language";

describe("pickLanguage", () => {
  it("keeps the viewer's own choice over the browser's language", () => {
    expect(pickLanguage("cs", "en-US")).toBe("cs");
    expect(pickLanguage("en", "cs-CZ")).toBe("en");
  });

  it("takes the browser's language when it is English or Czech", () => {
    expect(pickLanguage(null, "cs-CZ")).toBe("cs");
    expect(pickLanguage(null, "cs")).toBe("cs");
    expect(pickLanguage(null, "en-GB")).toBe("en");
  });

  it("falls back to English for any other browser language", () => {
    expect(pickLanguage(null, "sk-SK")).toBe("en");
    expect(pickLanguage(null, "de")).toBe("en");
    expect(pickLanguage(null, undefined)).toBe("en");
  });

  it("ignores a stored value that is not a supported language", () => {
    expect(pickLanguage("de", "cs-CZ")).toBe("cs");
  });
});
