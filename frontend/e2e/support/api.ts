import type { APIRequestContext } from "@playwright/test";
import { expect } from "@playwright/test";

// The API for the setup the UI adds no coverage to: it is the same origin as
// the app, behind the same Caddy (ADR-005). Only what the e2e needs is typed.

export interface Organizer {
  email: string;
  password: string;
}

/** Logs in over HTTP and returns an access token (ADR-006). */
export async function accessTokenOf(
  request: APIRequestContext,
  { email, password }: Organizer,
): Promise<string> {
  const response = await request.post("/api/v1/auth/login", {
    data: { email, password },
  });
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

/** Adds the players to the league's list, one request each, in order. */
export async function addPlayers(
  request: APIRequestContext,
  token: string,
  leagueId: string,
  names: readonly string[],
): Promise<void> {
  for (const name of names) {
    const response = await request.post(`/api/v1/leagues/${leagueId}/players`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { name },
    });
    expect(response.status(), `adding ${name}`).toBe(201);
  }
}

/**
 * Starts the tournament as the review's "Generate and start" does: with the
 * draw counter its setup shows now (FR-035). A stand-in while that button is
 * disabled by a missing route; see the spec.
 */
export async function startTournament(
  request: APIRequestContext,
  token: string,
  leagueId: string,
  tournamentId: string,
): Promise<void> {
  const base = `/api/v1/leagues/${leagueId}/tournaments/${tournamentId}`;
  const headers = { Authorization: `Bearer ${token}` };
  const setup = await request.get(`${base}/setup`, { headers });
  expect(setup.status()).toBe(200);
  const { draw_counter } = (await setup.json()) as { draw_counter: number };
  const started = await request.post(`${base}/start`, {
    headers,
    data: { expected_draw_counter: draw_counter },
  });
  expect(started.status()).toBe(200);
}
