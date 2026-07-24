import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { components } from '../api/schema'

type Tournament = components['schemas']['Tournament']
type TournamentCreate = components['schemas']['TournamentCreate']
type Match = components['schemas']['Match']
type TournamentOverview = components['schemas']['TournamentOverview']

function useTournaments(orgId: string | null) {
  return useQuery<Tournament[]>({
    queryKey: ['tournaments', orgId],
    queryFn: () => apiClient('/tournaments', 'get') as Promise<Tournament[]>,
    enabled: !!orgId,
  })
}

function useTournament(id: string) {
  return useQuery<Tournament>({
    queryKey: ['tournaments', id],
    queryFn: () => apiClient('/tournaments/{tournamentId}', 'get') as Promise<Tournament>,
    enabled: !!id,
  })
}

function useTournamentOverview(id: string) {
  return useQuery<TournamentOverview>({
    queryKey: ['tournament-overview', id],
    queryFn: () => apiClient('/tournaments/{tournamentId}/overview', 'get') as Promise<TournamentOverview>,
    enabled: !!id,
    refetchInterval: 5000,
  })
}

function useCreateTournament() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TournamentCreate) =>
      apiClient('/tournaments', 'post', { body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments'] })
    },
  })
}

function useSeedTournament(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { method: 'random' | 'manual'; order?: string[] }) =>
      apiClient('/tournaments/{tournamentId}/seed', 'post', {
        body: JSON.stringify({ method: args.method, order: args.order }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments', id] })
      qc.invalidateQueries({ queryKey: ['tournament-overview', id] })
    },
  })
}

function useGenerateBracket(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient('/tournaments/{tournamentId}/generate-bracket', 'post'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments', id] })
      qc.invalidateQueries({ queryKey: ['tournament-overview', id] })
    },
  })
}

export {
  useTournaments,
  useTournament,
  useTournamentOverview,
  useCreateTournament,
  useSeedTournament,
  useGenerateBracket,
}
export type { Tournament, TournamentCreate, Match, TournamentOverview }
