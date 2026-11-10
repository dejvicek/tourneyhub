// The one route table (docs/frontend-style.md §9). Screens load lazily; the
// build groups each feature folder into one chunk (vite.config.ts), so an
// area costs one request, not one per screen. A screen's number is its frame
// in the Figma file's "Tournament lifecycle" page.
//
// `lazy` is a function, not an object: React Router clears a lazy object's
// properties in place once loaded, which would break a second router built
// from this table, as the tests build one per test.
import type { RouteObject } from "react-router";
import { Navigate } from "react-router";

import { AppShell } from "@/components/AppShell";
import { PageFallback } from "@/components/PageFallback";
import { RouteError } from "@/components/RouteError";
import { paths } from "@/lib/paths";
import { HomePage } from "@/pages/HomePage";
import { NotFoundPage } from "@/pages/NotFoundPage";

export const routes: RouteObject[] = [
  {
    HydrateFallback: PageFallback,
    ErrorBoundary: RouteError,
    children: [
      {
        Component: AppShell,
        children: [
          { index: true, Component: HomePage },
          {
            ErrorBoundary: RouteError,
            children: [
              {
                path: paths.login,
                lazy: async () => ({
                  Component: (await import("@/features/auth/LoginPage"))
                    .LoginPage,
                }),
              },
              {
                path: paths.signUp,
                lazy: async () => ({
                  Component: (await import("@/features/auth/SignUpPage"))
                    .SignUpPage,
                }),
              },
              {
                path: paths.myLeagues,
                lazy: async () => ({
                  Component: (await import("@/features/leagues/MyLeaguesPage"))
                    .MyLeaguesPage,
                }),
              },
            ],
          },
          {
            ErrorBoundary: RouteError,
            children: [
              {
                path: paths.publicLeague,
                lazy: async () => ({
                  Component: (
                    await import("@/features/public/PublicLeaguePage")
                  ).PublicLeaguePage,
                }),
              },
              {
                path: paths.publicTournament,
                lazy: async () => ({
                  Component: (
                    await import("@/features/public/PublicTournamentPage")
                  ).PublicTournamentPage,
                }),
              },
            ],
          },
          { path: "*", Component: NotFoundPage },
        ],
      },
      {
        path: paths.league,
        lazy: async () => ({
          Component: (await import("@/features/leagues/LeagueShell"))
            .LeagueShell,
        }),
        ErrorBoundary: RouteError,
        children: [
          { index: true, element: <Navigate to="tournaments" replace /> },
          {
            path: paths.tournaments, // 1
            lazy: async () => ({
              Component: (
                await import("@/features/tournaments/TournamentsPage")
              ).TournamentsPage,
            }),
          },
          {
            path: paths.newTournament, // 2
            lazy: async () => ({
              Component: (
                await import("@/features/tournaments/SetupFormatPage")
              ).SetupFormatPage,
            }),
          },
          {
            path: paths.setupPlayers, // 3
            lazy: async () => ({
              Component: (
                await import("@/features/tournaments/SetupPlayersPage")
              ).SetupPlayersPage,
            }),
          },
          {
            path: paths.setupDraw, // 4
            lazy: async () => ({
              Component: (await import("@/features/tournaments/SetupDrawPage"))
                .SetupDrawPage,
            }),
          },
          {
            path: paths.setupReview, // 5
            lazy: async () => ({
              Component: (
                await import("@/features/tournaments/SetupReviewPage")
              ).SetupReviewPage,
            }),
          },
          {
            path: paths.tournament, // 6
            lazy: async () => ({
              Component: (await import("@/features/tournaments/RoundRobinPage"))
                .RoundRobinPage,
            }),
          },
          {
            path: paths.fields, // 6b
            lazy: async () => ({
              Component: (await import("@/features/fields/FieldsPage"))
                .FieldsPage,
            }),
          },
          {
            path: paths.moveMatch, // 6c
            lazy: async () => ({
              Component: (await import("@/features/fields/MoveMatchPage"))
                .MoveMatchPage,
            }),
          },
          {
            path: paths.editFields, // 6d
            lazy: async () => ({
              Component: (await import("@/features/fields/EditFieldsPage"))
                .EditFieldsPage,
            }),
          },
          {
            path: paths.enterResult, // 7
            lazy: async () => ({
              Component: (await import("@/features/results/EnterResultPage"))
                .EnterResultPage,
            }),
          },
          {
            path: paths.bestOfResult, // 7b
            lazy: async () => ({
              Component: (await import("@/features/results/BestOfResultPage"))
                .BestOfResultPage,
            }),
          },
          {
            path: paths.groupPhaseDone, // 8
            lazy: async () => ({
              Component: (
                await import("@/features/tournaments/GroupPhaseDonePage")
              ).GroupPhaseDonePage,
            }),
          },
          {
            path: paths.knockout, // 9
            lazy: async () => ({
              Component: (await import("@/features/tournaments/KnockoutPage"))
                .KnockoutPage,
            }),
          },
          {
            path: paths.finished, // 10
            lazy: async () => ({
              Component: (await import("@/features/tournaments/FinishedPage"))
                .FinishedPage,
            }),
          },
          {
            path: paths.betweenRounds, // 11
            lazy: async () => ({
              Component: (
                await import("@/features/tournaments/BetweenRoundsPage")
              ).BetweenRoundsPage,
            }),
          },
          {
            path: paths.lateAndDisabled, // 12
            lazy: async () => ({
              Component: (
                await import("@/features/tournaments/LateAndDisabledPage")
              ).LateAndDisabledPage,
            }),
          },
          {
            path: paths.startKnockout, // 13
            lazy: async () => ({
              Component: (
                await import("@/features/tournaments/StartKnockoutPage")
              ).StartKnockoutPage,
            }),
          },
          {
            path: paths.seasonStandings,
            lazy: async () => ({
              Component: (
                await import("@/features/standings/SeasonStandingsPage")
              ).SeasonStandingsPage,
            }),
          },
          {
            path: paths.players,
            lazy: async () => ({
              Component: (await import("@/features/players/PlayersPage"))
                .PlayersPage,
            }),
          },
          {
            path: paths.leagueSettings,
            lazy: async () => ({
              Component: (await import("@/features/leagues/LeagueSettingsPage"))
                .LeagueSettingsPage,
            }),
          },
        ],
      },
    ],
  },
];
