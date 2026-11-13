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

/**
 * Signs up over HTTP with the instance's sign-up code (FR-001) and returns an
 * access token: for a spec whose UI coverage starts later in the evening.
 */
export async function signUp(
  request: APIRequestContext,
  signupCode: string,
  { email, password }: Organizer,
  displayName: string,
): Promise<string> {
  const response = await request.post("/api/v1/auth/signup", {
    data: {
      signup_code: signupCode,
      email,
      display_name: displayName,
      password,
    },
  });
  expect(response.status(), "signing up").toBe(201);
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

/** Creates a league with its Season 1 (FR-010) and returns its id. */
export async function createLeague(
  request: APIRequestContext,
  token: string,
  name: string,
): Promise<string> {
  const response = await request.post("/api/v1/leagues", {
    headers: { Authorization: `Bearer ${token}` },
    data: { id: uuid7(), name },
  });
  expect(response.status(), "creating the league").toBe(201);
  const body = (await response.json()) as { id: string };
  return body.id;
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
  const setup = (await picked.json()) as {
    draw_counter: number;
    entries: { id: string; seed: number | null }[];
  };
  const started = await request.post(`${base}/${tournamentId}/start`, {
    headers,
    data: {
      expected_draw_counter: setup.draw_counter,
      expected_seed_order: setup.entries
        .toSorted((a, b) => (a.seed ?? 0) - (b.seed ?? 0))
        .map((entry) => entry.id),
    },
  });
  expect(started.status(), "starting the tournament").toBe(200);
  return tournamentId;
}

/**
 * Creates a Singles Swiss of the given players on two fields, BO1 and the
 * default sit-out points, lets the league ranking seed them and starts it
 * (FR-035): round 1 pairs the top half against the bottom half, and with an
 * odd number the lowest seed sits out (BR-055, BR-058). Returns the
 * tournament's id.
 */
export async function startSinglesSwiss(
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
      type: "singles",
      group_phase: "swiss",
      round_robin_legs: null,
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
  const setup = (await picked.json()) as {
    draw_counter: number;
    entries: { id: string; seed: number | null }[];
  };
  const started = await request.post(`${base}/${tournamentId}/start`, {
    headers,
    data: {
      expected_draw_counter: setup.draw_counter,
      expected_seed_order: setup.entries
        .toSorted((a, b) => (a.seed ?? 0) - (b.seed ?? 0))
        .map((entry) => entry.id),
    },
  });
  expect(started.status(), "starting the tournament").toBe(200);
  return tournamentId;
}

/**
 * Creates a Singles knockout without a group phase (FR-031) of the given
 * players on two fields, BO1 and no third-place match, and picks them; the
 * seeds follow the league ranking. Returns the tournament's id, in setup.
 */
export async function setUpKnockoutOnly(
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
      type: "singles",
      group_phase: "none",
      round_robin_legs: null,
      sit_out_points: null,
      group_match_format: null,
      knockout_match_format: "bo1",
      final_match_format: null,
      third_place_match: false,
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
  return tournamentId;
}

interface BracketMatch {
  match_id: string;
  number: number | null;
  state: string;
  sides: { entry_id: string | null; seed: number | null }[];
}

/**
 * Plays every knockout match over the API in match order, the better seed
 * winning 10:6; each result names the sides the bracket showed (BR-094).
 * Returns the number of matches played.
 */
export async function playBracket(
  request: APIRequestContext,
  token: string,
  leagueId: string,
  tournamentId: string,
): Promise<number> {
  const headers = { Authorization: `Bearer ${token}` };
  const tournament = `/api/v1/leagues/${leagueId}/tournaments/${tournamentId}`;
  let played = 0;
  for (;;) {
    const response = await request.get(`${tournament}/bracket`, { headers });
    expect(response.status()).toBe(200);
    const bracket = (await response.json()) as {
      rounds: { matches: BracketMatch[] }[];
    };
    const next = bracket.rounds
      .flatMap((round) => round.matches)
      .filter((match) => match.state === "ready" || match.state === "on_field")
      .toSorted((a, b) => (a.number ?? 0) - (b.number ?? 0))[0];
    if (next === undefined) {
      return played;
    }
    const [one, two] = next.sides.map((side) => side.seed ?? Infinity);
    const sideOne = (one ?? Infinity) < (two ?? Infinity);
    const result = await request.put(
      `${tournament}/matches/${next.match_id}/result`,
      {
        headers,
        data: {
          walkover_winner: null,
          games: [
            {
              winner: sideOne ? "side_1" : "side_2",
              score_1: sideOne ? 10 : 6,
              score_2: sideOne ? 6 : 10,
            },
          ],
          expected_sides: next.sides.map((side) => side.entry_id),
        },
      },
    );
    expect(result.status(), `result of match ${String(next.number)}`).toBe(200);
    played += 1;
  }
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
