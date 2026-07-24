import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { components } from '../api/schema'

type Season = components['schemas']['Season']
type Standing = components['schemas']['Standing']

function useSeason(id: string) {
  return useQuery<Season>({
    queryKey: ['seasons', id],
    queryFn: () => apiClient('/seasons/{seasonId}', 'get') as Promise<Season>,
    enabled: !!id,
  })
}

function useSeasonRankings(id: string) {
  return useQuery<Standing[]>({
    queryKey: ['season-rankings', id],
    queryFn: () => apiClient('/seasons/{seasonId}/rankings', 'get') as Promise<Standing[]>,
    enabled: !!id,
  })
}

function useTournamentStandings(tournamentId: string) {
  return useQuery<Standing[]>({
    queryKey: ['tournament-standings', tournamentId],
    queryFn: () =>
      apiClient('/tournaments/{tournamentId}/standings', 'get') as Promise<Standing[]>,
    enabled: !!tournamentId,
  })
}

export { useSeason, useSeasonRankings, useTournamentStandings }
