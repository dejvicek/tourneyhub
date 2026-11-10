import { setupServer } from "msw/node";

import { demoHandlers } from "@/demo/allHandlers";

/**
 * The network of every test: the demo's fake API (src/demo). A test changes
 * an answer with server.use(); an unhandled request fails the test.
 */
export const server = setupServer(...demoHandlers);
