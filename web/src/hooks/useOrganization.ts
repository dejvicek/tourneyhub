import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type { components } from '../api/schema'

type Organization = components['schemas']['Organization']

function useOrganizations() {
  return useQuery<Organization[]>({
    queryKey: ['organizations'],
    queryFn: () => apiClient('/organizations', 'get') as Promise<Organization[]>,
  })
}

function useOrganization(orgId: string) {
  return useQuery<Organization>({
    queryKey: ['organizations', orgId],
    queryFn: () => apiClient(`/organizations/${orgId}`, 'get') as Promise<Organization>,
    enabled: !!orgId,
  })
}

function useCreateOrganization() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; slug?: string }) =>
      apiClient('/organizations', 'post', { body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organizations'] })
    },
  })
}

function useTransferOwnership(orgId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (newOwnerUserId: string) =>
      apiClient(`/organizations/${orgId}/transfer-ownership`, 'post', {
        body: JSON.stringify({ newOwnerUserId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organizations', orgId] })
    },
  })
}

export { useOrganizations, useOrganization, useCreateOrganization, useTransferOwnership }
export type { Organization }
