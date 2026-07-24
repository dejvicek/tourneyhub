import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useTournamentStandings } from '../hooks/useSeason'
import { Table } from '../components/ui'

export default function StandingsPage() {
  const { t } = useTranslation()
  const { seasonId } = useParams<{ seasonId: string }>()
  const { data: standings, isLoading } = useTournamentStandings(seasonId || '')

  return (
    <div>
      <h1 className="font-heading text-2xl text-fg mb-6">{t('nav.standings')}</h1>
      {isLoading ? (
        <p className="text-fg-muted">{t('common.loading')}</p>
      ) : (
        <Table
          columns={[
            { key: 'rank', header: '#', sortable: true },
            { key: 'participantId', header: 'Player' },
            { key: 'points', header: 'Pts', sortable: true },
          ]}
          data={(standings || []) as unknown as Record<string, unknown>[]}
          emptyMessage={t('common.noData')}
        />
      )}
    </div>
  )
}
