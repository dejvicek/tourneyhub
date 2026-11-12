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

/** The league's players by name. */
export async function playerIdsOf(
  request: APIRequestContext,
  token: string,
  leagueId: string,
): Promise<Map<string, string>> {
  const response = await request.get(`/api/v1/leagues/${leagueId}/players`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { id: string; name: string }[];
  return new Map(body.map((player) => [player.name, player.id]));
}

/**
 * Creates a DYP round robin of the given players on two fields, lets the
 * league ranking draw the pairs and starts it; returns the tournament's id.
 */
export async function startDypRoundRobin(
  request: APIRequestContext,
  token: string,
  leagueId: string,
  { name, playerIds }: { name: string; playerIds: readonly string[] },
): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const base = `/api/v1/leagues/${leagueId}/tournaments`;
  const created = await request.post(base, {
    headers,
    data: {
      id: uuid7(),
      name,
      date: new Date().toISOString().slice(0, 10),
      type: "dyp",
      group_phase: "round_robin",
      round_robin_legs: 1,
      sit_out_points: null,
      group_match_format: "bo1",
      knockout_match_format: null,
      final_match_format: null,
      third_place_match: null,
      goals_per_game: 10,
      field_count: 2,
    },
  });
  expect(created.status(), "creating the tournament").toBe(201);
  const { tournament_id: tournamentId } = (await created.json()) as {
    tournament_id: string;
  };
  const picked = await request.put(`${base}/${tournamentId}/setup/players`, {
    headers,
    data: { player_ids: playerIds },
  });
  expect(picked.status(), "picking the players").toBe(200);
  const { draw_counter: drawCounter } = (await picked.json()) as {
    draw_counter: number;
  };
  const started = await request.post(`${base}/${tournamentId}/start`, {
    headers,
    data: { expected_draw_counter: drawCounter },
  });
  expect(started.status(), "starting the tournament").toBe(200);
  return tournamentId;
}

/** A UUIDv7, as a client makes one for a new tournament (ADR-008). */
function uuid7(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const millis = BigInt(Date.now());
  for (let i = 0; i < 6; i++) {
    bytes[i] = Number((millis >> BigInt(8 * (5 - i))) & 0xffn);
  }
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x70;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(
    "",
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
