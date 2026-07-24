import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useTournamentOverview, useSeedTournament, useGenerateBracket } from '../hooks/useTournament'
import { Button, Badge, Bracket, Table } from '../components/ui'
import type { Match } from '../hooks/useTournament'
import type { components } from '../api/schema'

type Standing = components['schemas']['Standing']

type Tab = 'bracket' | 'standings' | 'info'

export default function TournamentView() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data, isLoading } = useTournamentOverview(id!)
  const seed = useSeedTournament(id!)
  const generateBracket = useGenerateBracket(id!)
  const [tab, setTab] = useState<Tab>('bracket')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <p className="text-fg-muted">{t('common.loading')}</p>
      </div>
    )
  }

  if (!data?.tournament) return null

  const tournament = data.tournament
  const matches: Match[] = (data.matches as Match[]) || []
  const standings: Standing[] = (data.standings as Standing[]) || []

  const stateBadge = (state: string) => {
    const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'default'> = {
      Draft: 'default',
      RegistrationOpen: 'info',
      RegistrationClosed: 'warning',
      Seeded: 'warning',
      InProgress: 'info',
      Completed: 'success',
      Cancelled: 'danger',
    }
    return map[state] || 'default'
  }

  const bracketRounds = () => {
    const rounds = new Set<number>()
    matches.forEach((m) => rounds.add(m.round))
    return Array.from(rounds)
      .sort((a, b) => a - b)
      .map((r) => ({ round: r, label: `${t('tournament.round')} ${r}` }))
  }

  const bracketMatches = matches.map((m) => ({
    id: m.id,
    round: m.round,
    slot: m.slot,
    participantA: m.participantA ? { id: m.participantA, name: m.participantA } : null,
    participantB: m.participantB ? { id: m.participantB, name: m.participantB } : null,
    state: m.state,
    winnerId: m.result?.winnerId || null,
  }))

  const state = tournament.state as string
  const noParticipants = !matches || matches.length === 0

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="font-heading text-2xl text-fg">{tournament.disciplineName || tournament.id}</h1>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant={stateBadge(state)}>{state}</Badge>
            <span className="text-sm text-fg-muted">{t('tournament.format')}: {tournament.formatType}</span>
          </div>
        </div>
        <div className="flex gap-2">
          {state === 'Draft' && (
              <Button variant="secondary" size="sm" onClick={() => seed.mutate({ method: 'random' })}>
              Seed
            </Button>
          )}
          {state === 'Seeded' && (
            <Button variant="primary" size="sm" onClick={() => generateBracket.mutate()}>
              Generate Bracket
            </Button>
          )}
          <Button variant="secondary" size="sm">{t('tournament.share')}</Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border mb-6">
        {(
          [
            ['bracket', t('tournament.bracket')],
            ['standings', t('tournament.standings')],
            ['info', t('tournament.info')],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === key
                ? 'border-primary text-primary'
                : 'border-transparent text-fg-muted hover:text-fg'
            }`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Bracket Tab */}
      {tab === 'bracket' && (
        <div>
          {noParticipants && (
            <div className="flex items-center justify-center p-12 border border-border rounded-lg bg-bg-surface">
              <p className="text-fg-muted text-sm text-center">
                {state === 'Draft' && t('tournament.noParticipants')}
                {state === 'RegistrationOpen' && t('tournament.noParticipants')}
                {state === 'RegistrationClosed' && t('tournament.seedPrompt')}
              </p>
            </div>
          )}
          {!noParticipants && (
            <Bracket
              rounds={bracketRounds()}
              matches={bracketMatches}
              onMatchClick={(matchId) => navigate(`/tournaments/${id}/matches/${matchId}/result`)}
            />
          )}
        </div>
      )}

      {/* Standings Tab */}
      {tab === 'standings' && (
        <div>
          {standings.length === 0 ? (
            <div className="flex items-center justify-center p-12 border border-border rounded-lg bg-bg-surface">
              <p className="text-fg-muted text-sm">{t('tournament.noParticipants')}</p>
            </div>
          ) : (
            <Table
              columns={[
                { key: 'rank', header: '#', sortable: true },
                { key: 'participantId', header: 'Player' },
                { key: 'points', header: 'Pts', sortable: true },
              ]}
              data={standings as unknown as Record<string, unknown>[]}
            />
          )}
        </div>
      )}

      {/* Info Tab */}
      {tab === 'info' && (
        <div className="max-w-md">
          <div className="bg-bg-subtle rounded-md p-4 space-y-2 text-sm">
            {[
              [t('tournament.format'), tournament.formatType],
              [t('tournament.discipline'), tournament.disciplineName],
              [t('tournament.resultModel'), tournament.resultModel],
              [t('tournament.teamSize'), String(tournament.teamSize)],
              [t('tournament.resultEntryMode'), tournament.resultEntryMode],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between">
                <span className="text-fg-muted">{label}</span>
                <span className="text-fg font-medium">{value || '-'}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
