import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useCreateTournament } from '../hooks/useTournament'
import { useOrgContext } from '../hooks/useOrgContext'
import { Button, Input, Select } from '../components/ui'

const STEPS = ['basics', 'advanced', 'review'] as const
type Step = (typeof STEPS)[number]

export default function CreateTournamentWizard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const createTournament = useCreateTournament()
  const { activeOrgId } = useOrgContext()
  const [step, setStep] = useState<Step>('basics')
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const [name, setName] = useState('')
  const [discipline, setDiscipline] = useState('')
  const [format, setFormat] = useState<'SingleElimination' | 'RoundRobin'>('SingleElimination')
  const [resultModel, setResultModel] = useState<'winner' | 'score'>('winner')
  const [teamSize, setTeamSize] = useState(1)
  const [entryFeeAmount, setEntryFeeAmount] = useState('')
  const [entryFeeCurrency, setEntryFeeCurrency] = useState('EUR')
  const [maxParticipants, setMaxParticipants] = useState('')
  const [resultEntryMode, setResultEntryMode] = useState<'organizer' | 'playerSelfReport'>('organizer')
  const [error, setError] = useState('')

  const stepIdx = STEPS.indexOf(step)

  const handleNext = () => {
    if (stepIdx < STEPS.length - 1) setStep(STEPS[stepIdx + 1])
  }

  const handleBack = () => {
    if (stepIdx > 0) setStep(STEPS[stepIdx - 1])
  }

  const handleCreate = () => {
    if (!activeOrgId) {
      setError(t('org.noOrgsCta'))
      return
    }
    setError('')
    createTournament.mutate(
      {
        disciplineName: discipline,
        resultModel,
        teamSize,
        formatType: format,
        resultEntryMode,
        entryFee:
          entryFeeAmount
            ? { amountMinor: Math.round(parseFloat(entryFeeAmount) * 100), currency: entryFeeCurrency }
            : undefined,
      },
      {
        onSuccess: (data: unknown) => {
          const t = data as { id: string }
          navigate(`/tournaments/${t.id}`)
        },
        onError: (err: Error) => setError(err.message),
      },
    )
  }

  return (
    <div className="max-w-xl mx-auto">
      <h1 className="font-heading text-2xl text-fg mb-6">{t('tournament.create')}</h1>

      {!activeOrgId && (
        <div className="mb-6 p-4 border border-accent/30 rounded-md bg-accent/5 text-center">
          <p className="text-sm text-fg mb-2">{t('org.noOrgs')} {t('org.noOrgsCta')}</p>
          <Link to="/orgs/new">
            <Button variant="primary" size="sm">
              {t('org.create')}
            </Button>
          </Link>
        </div>
      )}

      {/* Step tabs */}
      <div className="flex border-b border-border mb-6">
        {STEPS.map((s) => (
          <button
            key={s}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              s === step
                ? 'border-primary text-primary'
                : 'border-transparent text-fg-muted hover:text-fg'
            }`}
            onClick={() => setStep(s)}
          >
            {t(`tournament.${s}`)}
          </button>
        ))}
      </div>

      {/* Step 1: Basics */}
      {step === 'basics' && (
        <div className="space-y-4">
          <Input
            label={t('tournament.name')}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <Input
            label={t('tournament.discipline')}
            type="text"
            value={discipline}
            onChange={(e) => setDiscipline(e.target.value)}
            hint="FIFA, Chess, Valorant, etc."
          />
          <Select
            label={t('tournament.format')}
            value={format}
            onChange={(e) => setFormat(e.target.value as 'SingleElimination' | 'RoundRobin')}
            options={[
              { value: 'SingleElimination', label: t('tournament.singleElimination') },
              { value: 'RoundRobin', label: t('tournament.roundRobin') },
            ]}
          />
          <Select
            label={t('tournament.resultModel')}
            value={resultModel}
            onChange={(e) => setResultModel(e.target.value as 'winner' | 'score')}
            options={[
              { value: 'winner', label: t('tournament.winner') },
              { value: 'score', label: t('tournament.score') },
            ]}
          />
          <Select
            label={t('tournament.teamSize')}
            value={String(teamSize)}
            onChange={(e) => setTeamSize(Number(e.target.value))}
            options={[
              { value: '1', label: t('tournament.individual') },
              { value: '2', label: '2' },
              { value: '3', label: '3' },
              { value: '5', label: '5' },
            ]}
          />
        </div>
      )}

      {/* Step 2: Advanced */}
      {step === 'advanced' && (
        <div className="space-y-4">
          <button
            className="w-full text-left text-sm font-medium text-fg flex items-center justify-between p-3 rounded-md bg-bg-subtle hover:bg-bg-subtle/80 transition-colors"
            onClick={() => setAdvancedOpen(!advancedOpen)}
          >
            <span>{t('tournament.advanced')}</span>
            <span className="text-fg-muted">{advancedOpen ? '\u25B2' : '\u25BC'}</span>
          </button>

          {advancedOpen && (
            <div className="space-y-4 mt-4">
              <div className="flex gap-2">
                <div className="flex-1">
                  <Input
                    label={t('tournament.entryFee')}
                    type="number"
                    value={entryFeeAmount}
                    onChange={(e) => setEntryFeeAmount(e.target.value)}
                    min="0"
                    step="0.01"
                  />
                </div>
                <Select
                  label="Currency"
                  value={entryFeeCurrency}
                  onChange={(e) => setEntryFeeCurrency(e.target.value)}
                  options={[
                    { value: 'EUR', label: 'EUR' },
                    { value: 'USD', label: 'USD' },
                    { value: 'CZK', label: 'CZK' },
                  ]}
                />
              </div>
              <Input
                label={t('tournament.maxParticipants')}
                type="number"
                value={maxParticipants}
                onChange={(e) => setMaxParticipants(e.target.value)}
                min="2"
              />
              <Select
                label={t('tournament.resultEntryMode')}
                value={resultEntryMode}
                onChange={(e) => setResultEntryMode(e.target.value as 'organizer' | 'playerSelfReport')}
                options={[
                  { value: 'organizer', label: t('tournament.organizer') },
                  { value: 'playerSelfReport', label: t('tournament.player') },
                ]}
              />
            </div>
          )}
        </div>
      )}

      {/* Step 3: Review */}
      {step === 'review' && (
        <div className="space-y-4">
          <h2 className="font-heading text-lg text-fg">{t('tournament.review')}</h2>
          <div className="bg-bg-subtle rounded-md p-4 space-y-2 text-sm">
            {[
              [t('tournament.name'), name],
              [t('tournament.discipline'), discipline || '-'],
              [t('tournament.format'), t(`tournament.${format === 'SingleElimination' ? 'singleElimination' : 'roundRobin'}`)],
              [t('tournament.resultModel'), t(`tournament.${resultModel}`)],
              [t('tournament.teamSize'), teamSize === 1 ? t('tournament.individual') : `${teamSize}`],
              [t('tournament.entryFee'), entryFeeAmount ? `${entryFeeAmount} ${entryFeeCurrency}` : '-'],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between">
                <span className="text-fg-muted">{label}</span>
                <span className="text-fg font-medium">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="mt-4">
          <p className="text-xs text-accent" role="alert">{error}</p>
        </div>
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between mt-8">
        <Button
          variant="ghost"
          size="md"
          onClick={handleBack}
          disabled={stepIdx === 0}
        >
          {t('common.back')}
        </Button>
        {step !== 'review' ? (
          <Button variant="primary" size="md" onClick={handleNext}>
            {t('common.next')}
          </Button>
        ) : (
          <Button
            variant="primary"
            size="md"
            loading={createTournament.isPending}
            onClick={handleCreate}
          >
            {t('tournament.create')}
          </Button>
        )}
      </div>
    </div>
  )
}
