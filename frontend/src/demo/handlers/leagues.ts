// Demo handlers: leagues, their settings and seasons (FR-007, FR-010–FR-013,
// FR-020, FR-021, FR-070). The backend serves these routes; the handlers
// follow its schema (src/api/schema.d.ts) so the demo and the tests still
// answer them.
import { demoId } from "../ids";
import { apiError, route } from "../route";
import { DEFAULT_PLACEMENT_POINTS } from "../rules";
import {
  activeSeason,
  db,
  findLeague,
  leagueRead,
  withoutLeague,
} from "../store";

const leagueNotFound = () => apiError(404, "league_not_found");
const seasonNotFound = () => apiError(404, "season_not_found");

function findSeason(leagueId: string, seasonId: string) {
  return db().seasons.find(
    (season) => season.id === seasonId && season.league_id === leagueId,
  );
}

function now(): string {
  return new Date().toISOString();
}

export const leagueHandlers = [
  // The organizer's own leagues, oldest first.
  route("get", "/api/v1/leagues", () =>
    db()
      .leagues.filter((row) => row.owner_id === db().me.id)
      .toSorted((a, b) => a.created_at.localeCompare(b.created_at))
      .map(({ id, name }) => ({ id, name })),
  ),

  route(
    "post",
    "/api/v1/leagues",
    ({ body }) => {
      const state = db();
      // ADR-008: a repeated create returns the existing league.
      const existing = findLeague(body.id);
      if (existing) {
        return existing.owner_id === state.me.id
          ? leagueRead(existing)
          : apiError(409, "league_id_taken");
      }
      const createdAt = now();
      const league = {
        id: body.id,
        name: body.name,
        draws_allowed: false,
        default_field_count: 1,
        default_match_format: "bo1" as const,
        default_goals_per_game: 10,
        share_token: crypto.randomUUID().replaceAll("-", ""),
        created_at: createdAt,
        updated_at: null,
        owner_id: state.me.id,
      };
      state.leagues.push(league);
      // FR-010: creating a league starts Season 1.
      state.seasons.push({
        id: demoId(Date.now()),
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
    if (!row) {
      return leagueNotFound();
    }
    row.name = body.name ?? row.name;
    row.draws_allowed = body.draws_allowed ?? row.draws_allowed;
    row.default_field_count =
      body.default_field_count ?? row.default_field_count;
    row.default_match_format =
      body.default_match_format ?? row.default_match_format;
    row.default_goals_per_game =
      body.default_goals_per_game ?? row.default_goals_per_game;
    row.updated_at = now();
    return leagueRead(row);
  }),

  // FR-013; a repeated delete is 404 (ADR-008).
  route("delete", "/api/v1/leagues/{league_id}", ({ params }) => {
    const state = db();
    if (!findLeague(params.league_id)) {
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
      const at = now();
      current.state = "closed";
      current.closed_at = at;
      const season = {
        id: demoId(Date.now()),
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
      season.name = body.name;
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
      if (season.state === "closed") {
        return apiError(409, "season_closed");
      }
      season.placement_points = body.placement_points;
      return withoutLeague(season);
    },
  ),
];
