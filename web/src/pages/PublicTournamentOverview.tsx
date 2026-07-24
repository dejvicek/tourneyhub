import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useTournamentOverview } from '../hooks/useTournament'
import { Bracket, Badge, Table } from '../components/ui'
import type { Match } from '../hooks/useTournament'
import type { components } from '../api/schema'

type Standing = components['schemas']['Standing']

export default function PublicTournamentOverview() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const { data, isLoading } = useTournamentOverview(id!)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <p className="text-fg-muted">{t('common.loading')}</p>
      </div>
    )
  }

  if (!data?.tournament) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <p className="text-fg-muted">{t('notFound')}</p>
      </div>
    )
  }

  const tournament = data.tournament
  const matches: Match[] = (data.matches as Match[]) || []
  const standings: Standing[] = (data.standings as Standing[]) || []

  const bracketMatches = matches.map((m) => ({
    id: m.id,
    round: m.round,
    slot: m.slot,
    participantA: m.participantA ? { id: m.participantA, name: m.participantA } : null,
    participantB: m.participantB ? { id: m.participantB, name: m.participantB } : null,
    state: m.state,
    winnerId: m.result?.winnerId || null,
  }))

  const rounds = [...new Set(matches.map((m) => m.round))]
    .sort((a, b) => a - b)
    .map((r) => ({ round: r, label: `${t('tournament.round')} ${r}` }))

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="font-heading text-2xl text-fg">{tournament.disciplineName || t('tournament.TBD')}</h1>
        <div className="flex items-center gap-2 mt-1">
          <Badge variant="info">{tournament.state}</Badge>
          <span className="text-sm text-fg-muted">{tournament.formatType}</span>
        </div>
      </div>

      <div className="space-y-8">
        {matches.length > 0 && (
          <section>
            <h2 className="font-heading text-lg text-fg mb-4">{t('tournament.bracket')}</h2>
            <Bracket rounds={rounds} matches={bracketMatches} />
          </section>
        )}

        {standings.length > 0 && (
          <section>
            <h2 className="font-heading text-lg text-fg mb-4">{t('tournament.standings')}</h2>
            <Table
              columns={[
                { key: 'rank', header: '#', sortable: true },
                { key: 'participantId', header: 'Player' },
                { key: 'points', header: 'Pts', sortable: true },
              ]}
              data={standings as unknown as Record<string, unknown>[]}
            />
          </section>
        )}
      </div>
    </div>
  )
}
