import { createBrowserRouter, Navigate } from 'react-router-dom'
import AuthLayout from './layouts/AuthLayout'
import AppLayout from './layouts/AppLayout'
import PublicLayout from './layouts/PublicLayout'
import LoginPage from './pages/auth/LoginPage'
import RegisterPage from './pages/auth/RegisterPage'
import VerifyEmailPage from './pages/auth/VerifyEmailPage'
import ResetPasswordPage from './pages/auth/ResetPasswordPage'
import DashboardPage from './pages/DashboardPage'
import ListOrgsPage from './pages/ListOrgsPage'
import CreateOrgPage from './pages/CreateOrgPage'
import OrgViewPage from './pages/OrgViewPage'
import ListTournamentsPage from './pages/ListTournamentsPage'
import CreateTournamentWizard from './pages/CreateTournamentWizard'
import TournamentView from './pages/TournamentView'
import MatchResultEntry from './pages/MatchResultEntry'
import ListLeaguesPage from './pages/ListLeaguesPage'
import CreateLeaguePage from './pages/CreateLeaguePage'
import LeagueViewPage from './pages/LeagueViewPage'
import PublicLeaguePage from './pages/PublicLeaguePage'
import PublicTournamentOverview from './pages/PublicTournamentOverview'
import SeasonViewPage from './pages/SeasonViewPage'
import RankingsPage from './pages/RankingsPage'
import StandingsPage from './pages/StandingsPage'
import ComponentShowcase from './pages/dev/ComponentShowcase'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/dashboard" replace />,
  },
  {
    element: <AuthLayout />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
      { path: '/verify-email', element: <VerifyEmailPage /> },
      { path: '/reset-password', element: <ResetPasswordPage /> },
    ],
  },
  {
    element: <AppLayout />,
    children: [
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/orgs', element: <ListOrgsPage /> },
      { path: '/orgs/new', element: <CreateOrgPage /> },
      { path: '/orgs/:orgId', element: <OrgViewPage /> },
      { path: '/tournaments', element: <ListTournamentsPage /> },
      { path: '/tournaments/new', element: <CreateTournamentWizard /> },
      { path: '/tournaments/:id', element: <TournamentView /> },
      { path: '/tournaments/:id/matches/:matchId/result', element: <MatchResultEntry /> },
      { path: '/leagues', element: <ListLeaguesPage /> },
      { path: '/leagues/new', element: <CreateLeaguePage /> },
      { path: '/leagues/:id', element: <LeagueViewPage /> },
      { path: '/s/:seasonId', element: <SeasonViewPage /> },
      { path: '/s/:seasonId/rankings', element: <RankingsPage /> },
      { path: '/s/:seasonId/standings', element: <StandingsPage /> },
      { path: '/dev/components', element: <ComponentShowcase /> },
    ],
  },
  {
    element: <PublicLayout />,
    children: [
      { path: '/public/leagues/:slug', element: <PublicLeaguePage /> },
      { path: '/public/tournaments/:id', element: <PublicTournamentOverview /> },
    ],
  },
])
