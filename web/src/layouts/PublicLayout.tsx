import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import LanguageSwitcher from '../components/LanguageSwitcher'

export default function PublicLayout() {
  const { t } = useTranslation()

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <header className="border-b border-border px-6 py-4">
        <div className="max-w-[1200px] mx-auto flex items-center justify-between">
          <h1 className="font-heading text-2xl text-primary tracking-wide">
            {t('layout.tourneyhub')}
          </h1>
          <LanguageSwitcher />
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-border px-6 py-4">
        <div className="max-w-[1200px] mx-auto text-center text-sm text-fg-muted">
          {t('layout.poweredBy')}
        </div>
      </footer>
    </div>
  )
}
