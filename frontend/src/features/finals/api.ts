import {
  type DataTag,
  mutationOptions,
  type QueryClient,
  queryOptions,
  skipToken,
} from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";
import type { DisabledWrite, LateEntryWrite } from "@/api/provisionalTypes";
import type { components } from "@/api/schema";
import { tournamentQueries } from "@/features/tournaments/api";
import type { MonsterKnockoutMode } from "@/lib/rules";

type KnockoutWrite = components["schemas"]["KnockoutWrite"];
type KnockoutDrawWrite = components["schemas"]["KnockoutDrawWrite"];

type FinalFormatWrite = components["schemas"]["FinalFormatWrite"];

type RoundCreate = components["schemas"]["RoundCreate"];

type TiebreakersWrite = components["schemas"]["TiebreakersWrite"];

// Provisional routes, "finals" section of the provisional paths
// (src/api/provisionalPaths.ts), except the places (P8), the season effect (P10a),
// the knockout (P10b) and the Swiss rounds and tie-breakers (P12), which the
// backend serves. The Swiss standings come from GET …/play (playQueries in
// features/fields/api.ts). Keys start with the entity (docs/style/frontend-style.md §8.1).
const tournamentKey = (leagueId: string, tournamentId: string) =>
  ["leagues", leagueId, "tournaments", tournamentId] as const;

const pathOf = (leagueId: string, tournamentId: string) => ({
  path: { league_id: leagueId, tournament_id: tournamentId },
});

export interface PreviewRequest {
  qualifiers: number;
  thirdPlaceMatch: boolean;
  mode: MonsterKnockoutMode | null;
}

export const finalsQueries = {
  bracket: (leagueId: string, tournamentId: string) =>
    queryOptions({
      queryKey: [...tournamentKey(leagueId, tournamentId), "bracket"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
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
      queryFn: ({ signal }) =>
        dataOf(
          api.GET(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/season-effect",
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
                api.GET(
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
          api.GET("/api/v1/leagues/{league_id}/players", {
            params: { path: { league_id: leagueId } },
            signal,
          }),
        ),
    }),
  /**
   * Every player of the league, removed ones too, for the names on past
   * results (BR-002: a removed player keeps their results). Its own key: the
   * lists under ["leagues", id, "players"] hold the active players only.
   */
  namedPlayers: (leagueId: string) =>
    queryOptions({
      queryKey: ["leagues", leagueId, "players", "with-removed"],
      queryFn: ({ signal }) =>
        dataOf(
          api.GET("/api/v1/leagues/{league_id}/players", {
            params: {
              path: { league_id: leagueId },
              query: { include_removed: true },
            },
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
  /**
   * Draws the next round (FR-040, FR-042); ADR-008: carries the round number
   * the organizer expects, so a repeated or stale request is refused.
   */
  addRound: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (body: RoundCreate) =>
        dataOf(
          api.POST(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/rounds",
            { params: { path: pathOf(leagueId, tournamentId).path }, body },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  /**
   * Deletes the newest round by its id (ADR-008, FR-046, BR-066); round 1
   * takes the tournament back to setup.
   */
  deleteRound: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (roundId: string) =>
        dataOf(
          api.DELETE(
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
  /**
   * The enabled tie-breakers in their order (FR-043, BR-072). Answers the
   * whole tournament; the settle reloads it and the standings of GET …/play.
   */
  setTiebreakers: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (body: TiebreakersWrite) =>
        dataOf(
          api.PUT(
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
  /** ADR-008: carries the phase the screen saw as current, the group phase. */
  drawKnockout: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (body: KnockoutWrite) =>
        dataOf(
          api.PUT(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout",
            { params: { path: pathOf(leagueId, tournamentId).path }, body },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  /** FR-045: draws the knockout's pairs again; ADR-008 carries the counter the screen saw. */
  drawKnockoutAgain: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (body: KnockoutDrawWrite) =>
        dataOf(
          api.POST(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout/draw",
            { params: { path: pathOf(leagueId, tournamentId).path }, body },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  /**
   * The final's own format, or null to play the knockout's, while the final
   * has no result (FR-054, BR-120). A target value, so a repeat is harmless.
   */
  setFinalFormat: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (body: FinalFormatWrite) =>
        dataOf(
          api.PUT(
            "/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout/final-format",
            { params: { path: pathOf(leagueId, tournamentId).path }, body },
          ),
        ),
      onSettled: () => settle(queryClient, leagueId),
    }),
  /** The knockout is deleted by its phase id (ADR-008, FR-046). */
  deleteKnockout: (
    queryClient: QueryClient,
    leagueId: string,
    tournamentId: string,
  ) =>
    mutationOptions({
      scope: scope(leagueId),
      mutationFn: (phaseId: string) =>
        dataOf(
          api.DELETE(
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
      // The bracket is gone: drop it, so that the refresh after the delete
      // does not ask for it again (404) before the screen leaves.
      // eslint-disable-next-line no-restricted-syntax -- drops the deleted bracket; onSettled reloads
      onSuccess: () => {
        queryClient.removeQueries({
          queryKey: [...tournamentKey(leagueId, tournamentId), "bracket"],
          exact: true,
        });
      },
      onSettled: () => settle(queryClient, leagueId),
    }),
};

// openapi-fetch turns the contract's tuples into arrays, so the screens type
// what they get from the queries (the same data the contract describes).
type QueryData<T extends { queryKey: unknown }> =
  T["queryKey"] extends DataTag<unknown, infer Data, unknown> ? Data : never;

type OrganizerBracket = QueryData<ReturnType<typeof finalsQueries.bracket>>;
type OrganizerMatch = OrganizerBracket["rounds"][number]["matches"][number];

// The bracket screens also draw the share link's bracket, which has no
// `result_locked` (it is the organizer's, BR-094), so there it is optional.
export type BracketMatchData = Omit<OrganizerMatch, "result_locked"> & {
  result_locked?: boolean;
};
export type BracketRoundData = Omit<
  OrganizerBracket["rounds"][number],
  "matches"
> & { matches: BracketMatchData[] };
export type BracketData = Omit<OrganizerBracket, "rounds"> & {
  rounds: BracketRoundData[];
};
export type BracketSideData = BracketMatchData["sides"][number];
export type PlacesData = QueryData<ReturnType<typeof finalsQueries.places>>;
export type PlaceData = PlacesData["rows"][number];
export type ParticipantData = QueryData<
  ReturnType<typeof finalsQueries.participants>
>[number];
export type PreviewData = QueryData<ReturnType<typeof finalsQueries.preview>>;
export type TournamentData = QueryData<
  ReturnType<typeof tournamentQueries.detail>
>;
