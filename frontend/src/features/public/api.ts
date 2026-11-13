import { queryOptions } from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";

// The share-link views (FR-070–FR-072): no account, read-only. The backend
// serves the league, a season's tournaments, a tournament, the season
// standings, the group phase's standings (a round robin's, or a Swiss's
// with BH1 and BH2, P12), the places (P11, P10a) and the knockout (P10b).

function fetchLeague(shareToken: string, signal?: AbortSignal) {
  return dataOf(
    api.GET("/api/v1/public/{share_token}", {
      params: { path: { share_token: shareToken } },
      signal,
    }),
  );
}

function fetchTournament(
  shareToken: string,
  tournamentId: string,
  signal?: AbortSignal,
) {
  return dataOf(
    api.GET("/api/v1/public/{share_token}/tournaments/{tournament_id}", {
      params: {
        path: { share_token: shareToken, tournament_id: tournamentId },
      },
      signal,
    }),
  );
}

/** A league as the share link answers it: name, seasons and players. */
export type PublicLeague = Awaited<ReturnType<typeof fetchLeague>>;
/** A player's name; removed players too, for past results. */
export type PublicPlayer = PublicLeague["players"][number];
/** A tournament as the share link answers it. */
export type PublicTournament = Awaited<ReturnType<typeof fetchTournament>>;
export type PublicMatch = PublicTournament["rounds"][number]["matches"][number];

/** Live views refresh on their own, so a viewer sees fields change (FR-070). */
const LIVE_MS = 15_000;
/**
 * The season standings change only when a tournament finishes, and each read
 * loads every finished tournament of the season, so they refresh more slowly.
 */
const SEASON_MS = 60_000;

export const publicQueries = {
  league: (shareToken: string) =>
    queryOptions({
      queryKey: ["public", shareToken],
      queryFn: ({ signal }) => fetchLeague(shareToken, signal),
      refetchInterval: LIVE_MS,
    }),
  /** A season's tournaments, newest first; those in setup never appear. */
  tournaments: (shareToken: string, seasonId: string) =>
    queryOptions({
      queryKey: ["public", shareToken, "seasons", seasonId, "tournaments"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/public/{share_token}/seasons/{season_id}/tournaments",
            {
              params: {
                path: { share_token: shareToken, season_id: seasonId },
              },
              signal,
            },
          ),
        ),
      refetchInterval: LIVE_MS,
    }),
  /** The season standings (FR-070, FR-061). */
  seasonStandings: (shareToken: string, seasonId: string) =>
    queryOptions({
      queryKey: ["public", shareToken, "seasons", seasonId, "standings"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/public/{share_token}/seasons/{season_id}/standings",
            {
              params: {
                path: { share_token: shareToken, season_id: seasonId },
              },
              signal,
            },
          ),
        ),
      refetchInterval: SEASON_MS,
    }),
  tournament: (shareToken: string, tournamentId: string) =>
    queryOptions({
      queryKey: ["public", shareToken, "tournaments", tournamentId],
      queryFn: ({ signal }) =>
        fetchTournament(shareToken, tournamentId, signal),
      refetchInterval: LIVE_MS,
    }),
  /** The group phase's standings now: a round robin's or a Swiss's (FR-060, FR-043). */
  standings: (shareToken: string, tournamentId: string) =>
    queryOptions({
      queryKey: [
        "public",
        shareToken,
        "tournaments",
        tournamentId,
        "standings",
      ],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/public/{share_token}/tournaments/{tournament_id}/standings",
            {
              params: {
                path: { share_token: shareToken, tournament_id: tournamentId },
              },
              signal,
            },
          ),
        ),
      refetchInterval: LIVE_MS,
    }),
  /** The knockout; only a tournament with one has a bracket (404 otherwise). */
  bracket: (shareToken: string, tournamentId: string, enabled: boolean) =>
    queryOptions({
      queryKey: ["public", shareToken, "tournaments", tournamentId, "bracket"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/public/{share_token}/tournaments/{tournament_id}/bracket",
            {
              params: {
                path: { share_token: shareToken, tournament_id: tournamentId },
              },
              signal,
            },
          ),
        ),
      enabled,
      refetchInterval: LIVE_MS,
    }),
  /** The places decided so far, with the reason for each. */
  places: (shareToken: string, tournamentId: string, enabled: boolean) =>
    queryOptions({
      queryKey: ["public", shareToken, "tournaments", tournamentId, "places"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/public/{share_token}/tournaments/{tournament_id}/places",
            {
              params: {
                path: { share_token: shareToken, tournament_id: tournamentId },
              },
              signal,
            },
          ),
        ),
      enabled,
      refetchInterval: LIVE_MS,
    }),
};
