import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { components } from '../api/schema'

type RegistrationCreate = components['schemas']['RegistrationCreate']

function useCreateRegistration(tournamentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: RegistrationCreate) =>
      apiClient('/tournaments/{tournamentId}/registrations', 'post', {
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments', tournamentId] })
    },
  })
}

function useWithdrawParticipant(participantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient(`/participants/${participantId}/withdraw`, 'post'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments'] })
    },
  })
}

export { useCreateRegistration, useWithdrawParticipant }
