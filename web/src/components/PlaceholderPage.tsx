import { useTranslation } from 'react-i18next'

function PlaceholderPage({ title }: { title: string }) {
  const { t } = useTranslation()

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="bg-bg-surface border border-border rounded-lg p-8 shadow-md text-center">
        <h1 className="font-heading text-2xl text-fg mb-2">{title}</h1>
        <p className="text-fg-muted">{t('comingSoon')}</p>
      </div>
    </div>
  )
}

export default PlaceholderPage
