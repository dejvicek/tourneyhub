import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import LanguageSwitcher from '../components/LanguageSwitcher'

export default function AuthLayout() {
  const { t } = useTranslation()

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <div className="absolute top-4 right-4">
        <LanguageSwitcher />
      </div>
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <h1 className="font-heading text-4xl text-primary tracking-wide">
              {t('layout.tourneyhub')}
            </h1>
            <p className="text-fg-muted mt-2 text-sm">
              {t('layout.tagline')}
            </p>
          </div>
          <div className="bg-bg-surface border border-border rounded-lg p-8 shadow-md">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  )
}
