// The API client for routes the backend does not serve yet. It is typed by
// the generated schema plus the demo's provisional contract
// (src/demo/contract.ts), so that screens can be built against the demo's
// fake API now. Once the backend has a route, its calls move to `api` in
// client.ts and the route leaves the contract (src/demo/README.md).
import type { DemoPaths } from "@/demo/contract";

import { createApi } from "./client";

/**
 * Same origin and the same authentication as `api`: the paths carry
 * /api/v1 (ADR-005, ADR-006, ADR-008).
 */
export const provisionalApi = createApi<DemoPaths>();
