import { useContext } from 'react'
import { OrgContext } from './org-context'

export function useOrgContext() {
  const ctx = useContext(OrgContext)
  if (!ctx) throw new Error('useOrgContext must be used within OrgProvider')
  return ctx
}
