// Demo handlers: leagues and their settings (FR-007, FR-010, FR-011, FR-070).
import { demoId } from "../ids";
import { apiError, route } from "../route";
import { DEFAULT_PLACEMENT_POINTS } from "../rules";
import {
  activeSeason,
  db,
  findLeague,
  leagueSettings,
  leagueSummary,
} from "../store";

const notFound = (leagueId: string) =>
  apiError(404, "league_not_found", { league_id: leagueId });

export const leagueHandlers = [
  route("get", "/api/v1/leagues", () =>
    db()
      .leagues.filter((row) => row.owner_id === db().me.id)
      .flatMap((row) => leagueSummary(row) ?? []),
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
          ? existing.league
          : apiError(409, "league_id_taken", { id: body.id });
      }
      const league = {
        id: body.id,
        name: body.name,
        created_at: new Date().toISOString(),
        updated_at: null,
      };
      state.leagues.push({
        league,
        owner_id: state.me.id,
        settings: {
          draws_allowed: false,
          default_field_count: 1,
          default_match_format: "bo1",
          default_goals_per_game: 10,
          share_token: crypto.randomUUID().replaceAll("-", ""),
        },
      });
      // FR-010: creating a league starts Season 1.
      state.seasons.push({
        id: demoId(Date.now()),
        league_id: league.id,
        number: 1,
        name: null,
        state: "active",
        placement_points: [...DEFAULT_PLACEMENT_POINTS],
        started_at: league.created_at,
        closed_at: null,
      });
      return league;
    },
    201,
  ),

  route("get", "/api/v1/leagues/{league_id}", ({ params }) => {
    return findLeague(params.league_id)?.league ?? notFound(params.league_id);
  }),

  route("get", "/api/v1/leagues/{league_id}/settings", ({ params }) => {
    const row = findLeague(params.league_id);
    return row ? leagueSettings(row) : notFound(params.league_id);
  }),

  route("put", "/api/v1/leagues/{league_id}/settings", ({ params, body }) => {
    const row = findLeague(params.league_id);
    const season = activeSeason(params.league_id);
    if (!row || !season) {
      return notFound(params.league_id);
    }
    const { name, placement_points, ...settings } = body;
    row.league.name = name;
    row.league.updated_at = new Date().toISOString();
    row.settings = { ...row.settings, ...settings };
    season.placement_points = placement_points;
    return leagueSettings(row);
  }),
];
