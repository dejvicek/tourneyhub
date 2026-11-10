import { queryOptions } from "@tanstack/react-query";

import { dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";

// The share-link views (FR-070–FR-072): no account, read-only. The backend
// has no public routes yet (P11); these are the demo's contract.

function fetchTournament(
  shareToken: string,
  tournamentId: string,
  signal?: AbortSignal,
) {
  return dataOf(
    provisionalApi.GET(
      "/api/v1/public/{share_token}/tournaments/{tournament_id}",
      {
        params: {
          path: { share_token: shareToken, tournament_id: tournamentId },
        },
        signal,
      },
    ),
  );
}

/** A tournament as the share link answers it. */
export type PublicTournament = Awaited<ReturnType<typeof fetchTournament>>;
export type PublicMatch = PublicTournament["rounds"][number]["matches"][number];

/** Live views refresh on their own, so a viewer sees fields change (FR-070). */
const LIVE_MS = 15_000;

export const publicQueries = {
  league: (shareToken: string) =>
    queryOptions({
      queryKey: ["public", shareToken],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET("/api/v1/public/{share_token}", {
            params: { path: { share_token: shareToken } },
            signal,
          }),
        ),
      refetchInterval: LIVE_MS,
    }),
  tournament: (shareToken: string, tournamentId: string) =>
    queryOptions({
      queryKey: ["public", shareToken, "tournaments", tournamentId],
      queryFn: ({ signal }) =>
        fetchTournament(shareToken, tournamentId, signal),
      refetchInterval: LIVE_MS,
    }),
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
          provisionalApi.GET(
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
};
