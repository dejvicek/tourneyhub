import {
  type DataTag,
  mutationOptions,
  type QueryClient,
  queryOptions,
  skipToken,
} from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";
import type {
  DisabledWrite,
  KnockoutWrite,
  LateEntryWrite,
  RoundAddWrite,
  TiebreakersWrite,
} from "@/demo/contract";
import type { MonsterKnockoutMode } from "@/demo/rules";
import { tournamentQueries } from "@/features/tournaments/api";
import { providesProvisionalRoutes } from "@/lib/demoMode";

// Provisional routes of the demo's contract, "finals" section
// (src/demo/contract.ts), except the places, which the backend serves (P8). Keys start with the entity (docs/frontend-style.md §8.1).
const tournamentKey = (leagueId: string, tournamentId: string) =>
  ["leagues", leagueId, "tournaments", tournamentId] as const;

const pathOf = (leagueId: string, tournamentId: string) => ({
  path: { league_id: leagueId, tournament_id: tournamentId },
});

export interface PreviewRequest {
  qualifiers: number;
  thirdPlaceMatch: boolean;
  mode: MonsterKnockoutMode | null;
  draw: number;
}

export const finalsQueries = {
  bracket: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: [...tournamentKey(leagueId, tournamentId), "bracket"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/bracket",
            { params: pathOf(leagueId, tournamentId), signal },
          ),
        ),
    }),
  places: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: [...tournamentKey(leagueId, tournamentId), "places"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/places",
            { params: pathOf(leagueId, tournamentId), signal },
          ),
        ),
    }),
  seasonEffect: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: [...tournamentKey(leagueId, tournamentId), "season-effect"],
      // The backend serves this with P10; outside demo mode it stays off.
      enabled: providesProvisionalRoutes(),
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/season-effect",
            { params: pathOf(leagueId, tournamentId), signal },
          ),
        ),
    }),
  ranking: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: [...tournamentKey(leagueId, tournamentId), "ranking"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/ranking",
            { params: pathOf(leagueId, tournamentId), signal },
          ),
        ),
    }),
  participants: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: [...tournamentKey(leagueId, tournamentId), "participants"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/participants",
            { params: pathOf(leagueId, tournamentId), signal },
          ),
        ),
    }),
  /** Waits until the request is known. */
  preview: (
    leagueId: string,
    tournamentId: string,
    request: PreviewRequest | undefined,
  ) =>
    queryOptions({
      queryKey: [
        ...tournamentKey(leagueId, tournamentId),
        "knockout-preview",
        request,
      ],
      queryFn:
        request === undefined
          ? skipToken
          : ({ signal }) =>
              dataOf(
                provisionalApi.GET(
                  "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout/preview",
                  {
                    params: {
                      ...pathOf(leagueId, tournamentId),
                      query: {
                        qualifiers: request.qualifiers,
                        third_place_match: request.thirdPlaceMatch,
                        ...(request.mode === null
                          ? {}
                          : { mode: request.mode }),
                        draw: request.draw,
                      },
                    },
                    signal,
                  },
                ),
              ),
    }),
  players: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "players"],
      queryFn: ({ signal }) =>
        dataOf(
          provisionalApi.GET("/api/v1/leagues/{league_id}/players", {
            params: { path: { league_id: leagueId } },
            signal,
          }),
        ),
    }),
};

function settle(queryClient: QueryClient, leagueId: string) {
  return queryClient.invalidateQueries({ queryKey: ["leagues", leagueId] });
}

const scope = (leagueId: string) => ({ id: `league:${leagueId}` });

export const finalsMutations = {
  /** ADR-008: carries the round number the organizer expects. */
  addRound: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (body: RoundAddWrite) =>
        dataOf(
          provisionalApi.POST(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/rounds",
            { params: { path: pathOf(leagueId, tournamentId).path }, body },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  /** A round is deleted by its id (ADR-008). */
  deleteRound: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (roundId: string) =>
        dataOf(
          provisionalApi.DELETE(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/rounds/{round_id}",
            {
              params: {
                path: {
                  league_id: leagueId,
                  tournament_id: tournamentId,
                  round_id: roundId,
                },
              },
            },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  /** The target state: disabled or not, never a toggle. */
  setDisabled: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (variables: { entryId: string } & DisabledWrite) =>
        dataOf(
          provisionalApi.PUT(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/entries/{entry_id}/disabled",
            {
              params: {
                path: {
                  league_id: leagueId,
                  tournament_id: tournamentId,
                  entry_id: variables.entryId,
                },
              },
              body: { disabled: variables.disabled },
            },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  addLatePlayer: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (body: LateEntryWrite) =>
        dataOf(
          provisionalApi.POST(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/entries",
            { params: { path: pathOf(leagueId, tournamentId).path }, body },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  setTiebreakers: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (body: TiebreakersWrite) =>
        dataOf(
          provisionalApi.PUT(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/tiebreakers",
            { params: { path: pathOf(leagueId, tournamentId).path }, body },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  finish: (queryClient: QueryClient, leagueId: string, tournamentId: string) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: () =>
        dataOf(
          provisionalApi.PUT(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/state",
            {
              params: { path: pathOf(leagueId, tournamentId).path },
              body: { state: "finished" },
            },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  drawKnockout: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (body: KnockoutWrite) =>
        dataOf(
          provisionalApi.PUT(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout",
            { params: { path: pathOf(leagueId, tournamentId).path }, body },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  deleteKnockout: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (phaseId: string) =>
        dataOf(
          provisionalApi.DELETE(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/phases/{phase_id}",
            {
              params: {
                path: {
                  league_id: leagueId,
                  tournament_id: tournamentId,
                  phase_id: phaseId,
                },
              },
            },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
};

// openapi-fetch turns the contract's tuples into arrays, so the screens type
// what they get from the queries (the same data the contract describes).
type QueryData<T extends { queryKey: unknown }> =
  T["queryKey"] extends DataTag<unknown, infer Data, unknown> ? Data : never;

export type BracketData = QueryData<ReturnType<typeof finalsQueries.bracket>>;
export type BracketRoundData = BracketData["rounds"][number];
export type BracketMatchData = BracketRoundData["matches"][number];
export type BracketSideData = BracketMatchData["sides"][number];
export type PlacesData = QueryData<ReturnType<typeof finalsQueries.places>>;
export type PlaceData = PlacesData["rows"][number];
export type RankingData = QueryData<ReturnType<typeof finalsQueries.ranking>>;
export type ParticipantData = QueryData<
  ReturnType<typeof finalsQueries.participants>
>[number];
export type PreviewData = QueryData<ReturnType<typeof finalsQueries.preview>>;
export type TournamentData = QueryData<
  ReturnType<typeof tournamentQueries.detail>
>;
