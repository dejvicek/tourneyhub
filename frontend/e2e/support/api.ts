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

export interface MatchOf {
  id: string;
  round_no: number;
  position: number;
  outcome: string | null;
}

/** The tournament's matches in schedule order (round, then position). */
export async function matchesOf(
  request: APIRequestContext,
  token: string,
  leagueId: string,
  tournamentId: string,
): Promise<MatchOf[]> {
  const response = await request.get(
    `/api/v1/leagues/${leagueId}/tournaments/${tournamentId}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(response.status()).toBe(200);
  const body = (await response.json()) as {
    rounds: {
      round_no: number;
      matches: { id: string; position: number; outcome: string | null }[];
    }[];
  };
  return body.rounds
    .toSorted((a, b) => a.round_no - b.round_no)
    .flatMap((round) =>
      round.matches
        .toSorted((a, b) => a.position - b.position)
        .map((match) => ({ ...match, round_no: round.round_no })),
    );
}

/**
 * Enters a BO1 result in which side 1 wins `goals` to `against`: the bulk of
 * the evening, which the UI has no extra coverage to add to.
 */
export async function enterResult(
  request: APIRequestContext,
  token: string,
  leagueId: string,
  tournamentId: string,
  matchId: string,
  { goals, against }: { goals: number; against: number },
): Promise<void> {
  const response = await request.put(
    `/api/v1/leagues/${leagueId}/tournaments/${tournamentId}/matches/${matchId}/result`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        walkover_winner: null,
        games: [{ winner: "side_1", score_1: goals, score_2: against }],
      },
    },
  );
  expect(response.status(), `result of ${matchId}`).toBe(200);
}

export interface FieldsOf {
  /** Each field's number with the match on it, lowest number first. */
  fields: { id: string; number: number; match_id: string | null }[];
  /** The waiting list, in the order the matches get a field (FR-092). */
  waiting: string[];
  /** Every player of each match. */
  players: Map<string, string[]>;
}

/** The tournament's fields, waiting list and the players of its matches. */
export async function fieldsOf(
  request: APIRequestContext,
  token: string,
  leagueId: string,
  tournamentId: string,
): Promise<FieldsOf> {
  const response = await request.get(
    `/api/v1/leagues/${leagueId}/tournaments/${tournamentId}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(response.status()).toBe(200);
  const body = (await response.json()) as {
    fields: FieldsOf["fields"];
    waiting: string[];
    rounds: {
      matches: { id: string; sides: { player_ids: string[] }[] }[];
    }[];
  };
  return {
    fields: body.fields.toSorted((a, b) => a.number - b.number),
    waiting: body.waiting,
    players: new Map(
      body.rounds.flatMap((round) =>
        round.matches.map((match) => [
          match.id,
          match.sides.flatMap((side) => side.player_ids),
        ]),
      ),
    ),
  };
}
