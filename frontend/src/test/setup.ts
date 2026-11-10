import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, vi } from "vitest";

import { resetDemoStore } from "@/demo/store";

import { stubViewport } from "./media";
import { server } from "./server";

// The API clients send requests to their own origin, "/api/v1/…", as in the
// browser. Node's Request needs an absolute URL, so this one resolves them
// against jsdom's location. It is set before any test file imports a
// client, which keeps the Request class it finds.
const NodeRequest = globalThis.Request;
globalThis.Request = class extends NodeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(
      typeof input === "string" ? new URL(input, location.href) : input,
      init,
    );
  }
};

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
});

beforeEach(() => {
  // Phones first: a test that needs a wider layout stubs its own viewport.
  stubViewport(390);
  // jsdom has no ResizeObserver; Radix switches, checkboxes and radios inside
  // a <form> measure themselves with it.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {
        // Nothing is laid out in jsdom.
      }
      unobserve() {
        // Nothing is laid out in jsdom.
      }
      disconnect() {
        // Nothing is laid out in jsdom.
      }
    },
  );
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  server.resetHandlers();
  resetDemoStore();
});

afterAll(() => {
  server.close();
});
