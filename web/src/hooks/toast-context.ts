import { createContext } from 'react'

export type ToastVariant = 'success' | 'error' | 'info'

export type Toast = {
  id: number
  message: string
  variant: ToastVariant
}

export type ToastContextType = {
  toast: (message: string, variant?: ToastVariant) => void
}

export const ToastContext = createContext<ToastContextType | null>(null)
