import { useTranslation } from 'react-i18next'

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()

  const toggle = () => {
    const next = i18n.language === 'cs' ? 'en' : 'cs'
    i18n.changeLanguage(next)
  }

  return (
    <button
      onClick={toggle}
      className="px-2 py-1 text-xs font-medium rounded border border-border text-fg-muted hover:text-fg hover:border-border-hover transition-colors uppercase"
    >
      {i18n.language === 'cs' ? 'EN' : 'CS'}
    </button>
  )
}
