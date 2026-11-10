import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { resetDemoStore } from "@/demo/store";

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

afterEach(() => {
  cleanup();
  localStorage.clear();
  server.resetHandlers();
  resetDemoStore();
});

afterAll(() => {
  server.close();
});
