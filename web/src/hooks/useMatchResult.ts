import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { components } from '../api/schema'

type Result = components['schemas']['Result']

function useUpdateMatchResult(matchId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { result: Result; version: number }) =>
      apiClient(`/matches/${matchId}/result`, 'patch', {
        body: JSON.stringify(args.result),
        headers: { 'If-Match': String(args.version) },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournament-overview'] })
      qc.invalidateQueries({ queryKey: ['tournaments'] })
    },
  })
}

function useForfeitMatch(matchId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient(`/matches/${matchId}/forfeit`, 'post'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournament-overview'] })
    },
  })
}

export { useUpdateMatchResult, useForfeitMatch }
