// The API client for routes the backend does not serve yet. It is typed by
// the generated schema plus the provisional paths
// (src/api/provisionalPaths.ts), so that screens can be built against the
// fake API now. Once the backend has a route, its calls move to `api` in
// client.ts and the route leaves the paths (src/test/fake/README.md).
import { createApi } from "./client";
import type { ProvisionalApiPaths } from "./provisionalPaths";

/**
 * Same origin and the same authentication as `api`: the paths carry
 * /api/v1 (ADR-005, ADR-006, ADR-008).
 */
export const provisionalApi = createApi<ProvisionalApiPaths>();
