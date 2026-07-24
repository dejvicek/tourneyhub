import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { components } from '../api/schema'

type League = components['schemas']['League']
type LeagueCreate = components['schemas']['LeagueCreate']
type SeasonCreate = components['schemas']['SeasonCreate']

function useLeagues() {
  return useQuery<League[]>({
    queryKey: ['leagues'],
    queryFn: () => apiClient('/leagues', 'get') as Promise<League[]>,
  })
}

function useLeague(id: string) {
  return useQuery<League>({
    queryKey: ['leagues', id],
    queryFn: () => apiClient('/leagues/{leagueId}', 'get') as Promise<League>,
    enabled: !!id,
  })
}

function useCreateLeague() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: LeagueCreate) =>
      apiClient('/leagues', 'post', { body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leagues'] }),
  })
}

function useCreateSeason(leagueId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SeasonCreate) =>
      apiClient(`/leagues/${leagueId}/seasons`, 'post', { body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leagues', leagueId] })
    },
  })
}

function useInviteUser(leagueId: string) {
  return useMutation({
    mutationFn: (body: { email?: string; role: string }) =>
      apiClient(`/leagues/${leagueId}/invitations`, 'post', { body: JSON.stringify(body) }),
  })
}

export { useLeagues, useLeague, useCreateLeague, useCreateSeason, useInviteUser }
