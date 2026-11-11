import { afterEach, describe, expect, it, vi } from "vitest";

import { newId } from "./newId";

const V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("newId", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses crypto.randomUUID when it exists", () => {
    expect(newId()).toMatch(V4);
  });

  it("builds a version 4 UUID from getRandomValues when randomUUID is missing", () => {
    vi.stubGlobal("crypto", {
      getRandomValues: crypto.getRandomValues.bind(crypto),
    });
    const ids = Array.from({ length: 50 }, () => newId());
    for (const id of ids) {
      expect(id).toMatch(V4);
    }
    expect(new Set(ids).size).toBe(50);
  });

  it("sets the version and variant bits whatever the random bytes are", () => {
    vi.stubGlobal("crypto", {
      getRandomValues: (bytes: Uint8Array) => bytes.fill(0xff),
    });
    expect(newId()).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff");
    vi.stubGlobal("crypto", {
      getRandomValues: (bytes: Uint8Array) => bytes.fill(0),
    });
    expect(newId()).toBe("00000000-0000-4000-8000-000000000000");
  });
});
