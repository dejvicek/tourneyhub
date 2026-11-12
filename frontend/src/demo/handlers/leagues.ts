// Demo handlers: leagues, their settings and seasons (FR-007, FR-010–FR-013,
// FR-020, FR-021, FR-070). The backend serves these routes; the handlers
// follow its schema (src/api/schema.d.ts) so the demo and the tests still
// answer them.
import { newId } from "@/lib/newId";

import { nameProblem, type Problem, validationFailed } from "../outsideErrors";
import { apiError, route } from "../route";
import { DEFAULT_PLACEMENT_POINTS } from "../rules";
import {
  activeSeason,
  db,
  findLeague,
  leagueRead,
  outsideDb,
  withoutLeague,
} from "../store";

const leagueNotFound = () => apiError(404, "league_not_found");
const seasonNotFound = () => apiError(404, "season_not_found");

function findSeason(leagueId: string, seasonId: string) {
  return db().seasons.find(
    (season) => season.id === seasonId && season.league_id === leagueId,
  );
}

const INT_MAX = 2 ** 31 - 1;

/** The signed-in organizer: the demo's refresh session (handlers/auth.ts). */
function organizerId(): string | null {
  return outsideDb().signedInUserId;
}

/** P5a's PlacementPoints rule (FR-011), first problem only, as Pydantic stops. */
function placementProblem(points: unknown[]): Problem | undefined {
  const loc = ["body", "placement_points"];
  if (points.length === 0) {
    return { loc, type: "too_short" };
  }
  if (points.length > 256) {
    return { loc, type: "too_long" };
  }
  for (const [index, value] of points.entries()) {
    if (typeof value !== "number") {
      return { loc: [...loc, index], type: "int_type" };
    }
    if (!Number.isInteger(value)) {
      return { loc: [...loc, index], type: "int_from_float" };
    }
    if (value < 0) {
      return { loc: [...loc, index], type: "greater_than_equal", ge: 0 };
    }
    if (value > INT_MAX) {
      return { loc: [...loc, index], type: "less_than_equal", le: INT_MAX };
    }
  }
  const increase = points.findIndex(
    (value, index) => index > 0 && Number(value) > Number(points[index - 1]),
  );
  return increase === -1
    ? undefined
    : { loc, type: "placement_points_increase", place: increase + 1 };
}

/** The most fields and goals per game P5a accepts (backend/openapi.json). */
const MAX_FIELDS = 32;
const MAX_GOALS = 99;

/** P5a's count rule for the field and goal defaults: 1 up to `max`. */
function countProblem(
  value: number | null | undefined,
  field: string,
  max: number,
): Problem | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  if (!Number.isInteger(value)) {
    return { loc: ["body", field], type: "int_from_float" };
  }
  if (value < 1) {
    return { loc: ["body", field], type: "greater_than_equal", ge: 1 };
  }
  return value > max
    ? { loc: ["body", field], type: "less_than_equal", le: max }
    : undefined;
}

function now(): string {
  return new Date().toISOString();
}

export const leagueHandlers = [
  // The organizer's own leagues, oldest first.
  route("get", "/api/v1/leagues", () => {
    const userId = organizerId();
    if (userId === null) {
      return apiError(401, "not_authenticated");
    }
    return db()
      .leagues.filter((row) => row.owner_id === userId)
      .toSorted(
        (a, b) =>
          Number(a.created_at > b.created_at) -
          Number(a.created_at < b.created_at),
      )
      .map(({ id, name }) => ({ id, name }));
  }),

  route(
    "post",
    "/api/v1/leagues",
    ({ body }) => {
      const state = db();
      const userId = organizerId();
      if (userId === null) {
        return apiError(401, "not_authenticated");
      }
      // ADR-008: a repeated create returns the existing league.
      const existing = findLeague(body.id);
      if (existing) {
        return existing.owner_id === userId
          ? leagueRead(existing)
          : apiError(409, "league_id_taken");
      }
      const problem = nameProblem(body.name, ["body", "name"]);
      if (problem) {
        return validationFailed([problem]);
      }
      const createdAt = now();
      const league = {
        id: body.id,
        name: body.name.trim(),
        draws_allowed: false,
        default_field_count: 1,
        default_match_format: "bo1" as const,
        default_goals_per_game: 10,
        share_token: newId().replaceAll("-", ""),
        created_at: createdAt,
        updated_at: null,
        owner_id: userId,
      };
      state.leagues.push(league);
      // FR-010: creating a league starts Season 1.
      state.seasons.push({
        id: newId(),
        league_id: league.id,
        number: 1,
        name: null,
        state: "active",
        placement_points: [...DEFAULT_PLACEMENT_POINTS],
        started_at: createdAt,
        closed_at: null,
      });
      return leagueRead(league);
    },
    201,
  ),

  route("get", "/api/v1/leagues/{league_id}", ({ params }) => {
    const row = findLeague(params.league_id);
    return row ? leagueRead(row) : leagueNotFound();
  }),

  // Each given value is a target state; null or absent leaves it (FR-011).
  route("patch", "/api/v1/leagues/{league_id}", ({ params, body }) => {
    const row = findLeague(params.league_id);
    if (row === undefined) {
      return leagueNotFound();
    }
    // FR-007: another organizer's league is not found.
    if (row.owner_id !== organizerId()) {
      return leagueNotFound();
    }
    const problems = [
      typeof body.name === "string"
        ? nameProblem(body.name, ["body", "name"])
        : undefined,
      countProblem(body.default_field_count, "default_field_count", MAX_FIELDS),
      countProblem(
        body.default_goals_per_game,
        "default_goals_per_game",
        MAX_GOALS,
      ),
    ].filter((problem) => problem !== undefined);
    if (problems.length > 0) {
      return validationFailed(problems);
    }
    const before = JSON.stringify(row);
    row.name = body.name?.trim() ?? row.name;
    row.draws_allowed = body.draws_allowed ?? row.draws_allowed;
    row.default_field_count =
      body.default_field_count ?? row.default_field_count;
    row.default_match_format =
      body.default_match_format ?? row.default_match_format;
    row.default_goals_per_game =
      body.default_goals_per_game ?? row.default_goals_per_game;
    // updated_at moves only when a value changes (P5a, target states).
    if (JSON.stringify(row) !== before) {
      row.updated_at = now();
    }
    return leagueRead(row);
  }),

  // FR-013; a repeated delete is 404 (ADR-008).
  route("delete", "/api/v1/leagues/{league_id}", ({ params }) => {
    const state = db();
    if (findLeague(params.league_id)?.owner_id !== organizerId()) {
      return leagueNotFound();
    }
    const other = (row: { league_id: string }) =>
      row.league_id !== params.league_id;
    state.leagues = state.leagues.filter((row) => row.id !== params.league_id);
    state.seasons = state.seasons.filter(other);
    state.players = state.players.filter(other);
    state.tournaments = state.tournaments.filter(other);
    return null;
  }),

  // FR-021: closes the active season and starts the next with its table.
  route(
    "post",
    "/api/v1/leagues/{league_id}/seasons",
    ({ params, body }) => {
      const current = activeSeason(params.league_id);
      if (!findLeague(params.league_id) || !current) {
        return leagueNotFound();
      }
      if (current.number !== body.expected_current_number) {
        return apiError(409, "season_number_changed", {
          current_number: current.number,
        });
      }
      // BR-010, which P5a leaves to P7: no new season while a tournament of
      // the current one is unfinished.
      const unfinished = db().tournaments.filter(
        (t) => t.season_id === current.id && t.state !== "finished",
      );
      if (unfinished.length > 0) {
        return apiError(422, "validation_failed", {
          rule: "BR-010",
          tournament_ids: unfinished.map((t) => t.id),
        });
      }
      const at = now();
      current.state = "closed";
      current.closed_at = at;
      const season = {
        id: newId(),
        league_id: params.league_id,
        number: current.number + 1,
        name: null,
        state: "active" as const,
        placement_points: [...current.placement_points],
        started_at: at,
        closed_at: null,
      };
      db().seasons.push(season);
      return withoutLeague(season);
    },
    201,
  ),

  // FR-020: closed seasons may be renamed too (BR-011).
  route(
    "put",
    "/api/v1/leagues/{league_id}/seasons/{season_id}/name",
    ({ params, body }) => {
      if (!findLeague(params.league_id)) {
        return leagueNotFound();
      }
      const season = findSeason(params.league_id, params.season_id);
      if (!season) {
        return seasonNotFound();
      }
      if (body.name !== null) {
        const problem = nameProblem(body.name, ["body", "name"]);
        if (problem) {
          return validationFailed([problem]);
        }
      }
      season.name = body.name === null ? null : body.name.trim();
      return withoutLeague(season);
    },
  ),

  // FR-011, BR-011: a closed season keeps its table.
  route(
    "put",
    "/api/v1/leagues/{league_id}/seasons/{season_id}/placement-points",
    ({ params, body }) => {
      if (!findLeague(params.league_id)) {
        return leagueNotFound();
      }
      const season = findSeason(params.league_id, params.season_id);
      if (!season) {
        return seasonNotFound();
      }
      // The body is validated first, as P5a's request model does.
      const problem = placementProblem(body.placement_points);
      if (problem) {
        return validationFailed([problem]);
      }
      if (season.state === "closed") {
        return apiError(409, "season_closed");
      }
      season.placement_points = body.placement_points;
      return withoutLeague(season);
    },
  ),
];
