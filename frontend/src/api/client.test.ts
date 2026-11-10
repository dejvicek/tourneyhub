import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, createApi, dataOf } from "./client";
import type { paths } from "./schema";
import { getAccessToken, onSessionEnded, setAccessToken } from "./token";

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

describe("authentication", () => {
  afterEach(() => {
    setAccessToken(null);
  });

  const league = (api: ReturnType<typeof createApi<paths>>) =>
    api.GET("/api/v1/leagues/{league_id}", {
      params: { path: { league_id: LEAGUE_ID } },
    });

  /**
   * A server whose token "old" has expired: league calls with any other
   * token succeed, and the refresh answers `refreshStatus` after a pause.
   */
  function server(refreshStatus: 200 | 401) {
    const calls: string[] = [];
    let release: () => void = () => undefined;
    const refreshed = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetch = vi.fn(async (request: Request) => {
      const { pathname } = new URL(request.url);
      const auth = request.headers.get("Authorization");
      calls.push(`${request.method} ${pathname} ${auth ?? "-"}`);
      if (pathname === "/api/v1/auth/refresh") {
        await refreshed;
        return refreshStatus === 200
          ? json(200, { access_token: "new" })
          : json(401, { code: "not_authenticated", detail: {} });
      }
      return auth === "Bearer old" || auth === null
        ? json(401, { code: "token_expired", detail: {} })
        : json(200, {
            id: LEAGUE_ID,
            name: "Thursday league",
            created_at: "2026-11-10T18:00:00Z",
            updated_at: null,
          });
    });
    const api = createApi({ baseUrl: "http://localhost", fetch });
    return { api, calls, release };
  }

  it("sends the access token as a Bearer header", async () => {
    setAccessToken("new");
    const { api, calls } = server(200);

    await dataOf(league(api));

    expect(calls).toEqual([`GET /api/v1/leagues/${LEAGUE_ID} Bearer new`]);
  });

  it("refreshes once for two parallel 401s and retries each request once", async () => {
    setAccessToken("old");
    const { api, calls, release } = server(200);

    const both = Promise.all([dataOf(league(api)), dataOf(league(api))]);
    await vi.waitFor(() => {
      expect(calls).toHaveLength(3);
    });
    release();
    const [first, second] = await both;

    expect(first.name).toBe("Thursday league");
    expect(second.name).toBe("Thursday league");
    expect(getAccessToken()).toBe("new");
    expect(calls.filter((call) => call.includes("/auth/refresh"))).toEqual([
      "POST /api/v1/auth/refresh -",
    ]);
    expect(calls.filter((call) => call.endsWith("Bearer new"))).toHaveLength(2);
  });

  it("ends the session when the refresh is refused", async () => {
    setAccessToken("old");
    const ended = vi.fn();
    const stop = onSessionEnded(ended);
    const { api, calls, release } = server(401);
    release();

    const call = dataOf(league(api));

    await expect(call).rejects.toMatchObject({
      status: 401,
      code: "token_expired",
    });
    expect(getAccessToken()).toBeNull();
    expect(ended).toHaveBeenCalledOnce();
    expect(calls).toHaveLength(2);
    stop();
  });

  it("never refreshes after a 401 from the login", async () => {
    const fetch = vi.fn(() =>
      Promise.resolve(json(401, { code: "not_authenticated", detail: {} })),
    );
    const api = createApi({ baseUrl: "http://localhost", fetch });

    const call = dataOf(
      api.POST("/api/v1/auth/login", {
        body: { email: "a@example.com", password: "wrong password here" },
      }),
    );

    await expect(call).rejects.toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledOnce();
  });
});
