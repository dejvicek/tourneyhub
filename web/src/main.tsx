import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { ToastProvider } from './hooks/ToastProvider'
import { OrgProvider } from './hooks/OrgProvider'
import './i18n'
import './index.css'

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <OrgProvider>
          <RouterProvider router={router} />
        </OrgProvider>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
)
