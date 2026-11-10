// The API client for routes the backend does not serve yet. It is typed by
// the generated schema plus the demo's provisional contract
// (src/demo/contract.ts), so that screens can be built against the demo's
// fake API now. Once the backend has a route, its calls move to `api` in
// client.ts and the route leaves the contract (src/demo/README.md).
import createClient from "openapi-fetch";

import type { DemoPaths } from "@/demo/contract";

import { globalFetch } from "./client";

/** Same origin as `api`: the paths carry /api/v1 (ADR-005, ADR-008). */
export const provisionalApi = createClient<DemoPaths>({ fetch: globalFetch });
