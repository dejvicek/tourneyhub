import { setupServer } from "msw/node";

import { demoHandlers } from "@/test/fake/allHandlers";

/**
 * The network of every test: the fake API (src/test/fake). A test changes
 * an answer with server.use(); an unhandled request fails the test.
 */
export const server = setupServer(...demoHandlers);
