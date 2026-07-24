import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useCreateLeague } from '../hooks/useLeague'
import { Button, Input, Select } from '../components/ui'

export default function CreateLeaguePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const createLeague = useCreateLeague()
  const [name, setName] = useState('')
  const [visibility, setVisibility] = useState<'public' | 'unlisted' | 'private'>('private')
  const [winPoints, setWinPoints] = useState('3')
  const [drawPoints, setDrawPoints] = useState('1')
  const [lossPoints, setLossPoints] = useState('0')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    createLeague.mutate(
      { name, visibility },
      {
        onSuccess: (data: unknown) => {
          const l = data as { id: string }
          navigate(`/leagues/${l.id}`)
        },
        onError: (err: Error) => setError(err.message),
      },
    )
  }

  return (
    <div className="max-w-md mx-auto">
      <h1 className="font-heading text-2xl text-fg mb-6">{t('league.create')}</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input label={t('league.name')} type="text" value={name} onChange={(e) => setName(e.target.value)} required />
        <Select
          label={t('league.visibility')}
          value={visibility}
          onChange={(e) => setVisibility(e.target.value as 'public' | 'unlisted' | 'private')}
          options={[
            { value: 'public', label: t('league.public') },
            { value: 'unlisted', label: t('league.unlisted') },
            { value: 'private', label: t('league.private') },
          ]}
        />

        <button
          type="button"
          className="w-full text-left text-sm font-medium text-fg flex items-center justify-between p-3 rounded-md bg-bg-subtle"
          onClick={() => setAdvancedOpen(!advancedOpen)}
        >
          <span>{t('league.scoringConfig')}</span>
          <span className="text-fg-muted">{advancedOpen ? '\u25B2' : '\u25BC'}</span>
        </button>

        {advancedOpen && (
          <div className="space-y-3 mt-2">
            <Input label={t('league.winPoints')} type="number" value={winPoints} onChange={(e) => setWinPoints(e.target.value)} />
            <Input label={t('league.drawPoints')} type="number" value={drawPoints} onChange={(e) => setDrawPoints(e.target.value)} />
            <Input label={t('league.lossPoints')} type="number" value={lossPoints} onChange={(e) => setLossPoints(e.target.value)} />
          </div>
        )}

        {error && <p className="text-xs text-accent" role="alert">{error}</p>}

        <Button variant="primary" size="md" type="submit" loading={createLeague.isPending} className="w-full">
          {t('league.createButton')}
        </Button>
      </form>
    </div>
  )
}
