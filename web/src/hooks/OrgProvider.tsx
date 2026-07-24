import { useState, useCallback, type ReactNode } from 'react'
import { OrgContext } from './org-context'

const STORAGE_KEY = 'tourneyhub_activeOrgId'

export function OrgProvider({ children }: { children: ReactNode }) {
  const [activeOrgId, setActiveOrgIdState] = useState<string | null>(() => {
    return localStorage.getItem(STORAGE_KEY)
  })

  const setActiveOrgId = useCallback((id: string | null) => {
    setActiveOrgIdState(id)
    if (id) {
      localStorage.setItem(STORAGE_KEY, id)
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [])

  return (
    <OrgContext.Provider value={{ activeOrgId, setActiveOrgId }}>
      {children}
    </OrgContext.Provider>
  )
}
