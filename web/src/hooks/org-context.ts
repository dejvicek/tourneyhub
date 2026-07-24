import { createContext } from 'react'

export type OrgContextType = {
  activeOrgId: string | null
  setActiveOrgId: (id: string | null) => void
}

export const OrgContext = createContext<OrgContextType | null>(null)
