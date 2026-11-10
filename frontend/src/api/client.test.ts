import { describe, expect, it } from "vitest";

import { ApiError, createApi, dataOf } from "./client";

const LEAGUE_ID = "019a6b0c-7d1e-7c3a-9f00-000000000001";

function apiAnswering(response: Response) {
  return createApi({
    baseUrl: "http://localhost",
    fetch: () => Promise.resolve(response),
  });
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("dataOf", () => {
  it("resolves with the data of a successful call", async () => {
    const league = {
      id: LEAGUE_ID,
      name: "Thursday league",
      created_at: "2026-11-10T18:00:00Z",
      updated_at: null,
    };
    const api = apiAnswering(json(200, league));

    const data = await dataOf(
      api.GET("/api/v1/leagues/{league_id}", {
        params: { path: { league_id: LEAGUE_ID } },
      }),
    );

    expect(data).toEqual(league);
  });

  it("rejects with the API's error code and detail", async () => {
    const api = apiAnswering(
      json(404, { code: "league_not_found", detail: { id: LEAGUE_ID } }),
    );

    const call = dataOf(
      api.GET("/api/v1/leagues/{league_id}", {
        params: { path: { league_id: LEAGUE_ID } },
      }),
    );

    await expect(call).rejects.toBeInstanceOf(ApiError);
    await expect(call).rejects.toMatchObject({
      status: 404,
      code: "league_not_found",
      detail: { id: LEAGUE_ID },
    });
  });

  it("rejects without a code when the body is not an API error", async () => {
    const api = apiAnswering(new Response("Bad Gateway", { status: 502 }));

    const call = dataOf(
      api.GET("/api/v1/leagues/{league_id}", {
        params: { path: { league_id: LEAGUE_ID } },
      }),
    );

    await expect(call).rejects.toMatchObject({ status: 502, code: undefined });
  });
});
