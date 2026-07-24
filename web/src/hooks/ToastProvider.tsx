import { type ReactNode, useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ToastContext, type Toast, type ToastVariant } from './toast-context'

const variantStyles: Record<ToastVariant, string> = {
  success: 'border-primary/30 bg-primary/10 text-primary',
  error: 'border-accent/30 bg-accent/10 text-accent',
  info: 'border-border bg-bg-surface text-fg',
}

const variantIcons: Record<ToastVariant, string> = {
  success: '\u2713',
  error: '\u2717',
  info: '\u2139',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const [toasts, setToasts] = useState<Toast[]>([])
  const idRef = useRef(0)

  const addToast = useCallback((message: string, variant: ToastVariant = 'info') => {
    const id = ++idRef.current
    setToasts((prev) => [...prev, { id, message, variant }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 5000)
  }, [])

  const dismiss = (id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`flex items-center gap-2 px-4 py-3 rounded-lg border shadow-md text-sm animate-slide-up ${variantStyles[toast.variant]}`}
            role="alert"
          >
            <span className="font-bold">{variantIcons[toast.variant]}</span>
            <span className="flex-1">{toast.message}</span>
            <button
              onClick={() => dismiss(toast.id)}
              className="opacity-60 hover:opacity-100 ml-2"
              aria-label={t('common.dismiss')}
            >
              <svg viewBox="0 0 24 24" className="w-4 h-4 fill-none stroke-current stroke-2" strokeLinecap="round">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
