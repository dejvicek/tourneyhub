import { useParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useSeason } from '../hooks/useSeason'
import { Badge, Card, Button } from '../components/ui'

export default function SeasonViewPage() {
  const { t } = useTranslation()
  const { seasonId } = useParams<{ seasonId: string }>()
  const { data: season, isLoading } = useSeason(seasonId!)

  if (isLoading) return <div className="flex items-center justify-center min-h-[40vh]"><p className="text-fg-muted">{t('common.loading')}</p></div>
  if (!season) return <div className="flex items-center justify-center min-h-[40vh]"><p className="text-fg-muted">{t('notFound')}</p></div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading text-2xl text-fg">{season.name}</h1>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant={season.state === 'active' ? 'success' : 'default'}>{t(`season.${season.state}`)}</Badge>
          </div>
        </div>
        <Link to={`/s/${season.id}/rankings`}>
          <Button variant="secondary" size="sm">{t('season.rankings')}</Button>
        </Link>
      </div>

      <div className="max-w-md">
        <Card padding="md" className="space-y-3 text-sm">
          <div className="flex justify-between"><span className="text-fg-muted">{t('season.startsAt')}</span><span className="text-fg">{season.startsAt ? new Date(season.startsAt).toLocaleDateString() : '-'}</span></div>
          <div className="flex justify-between"><span className="text-fg-muted">{t('season.endsAt')}</span><span className="text-fg">{season.endsAt ? new Date(season.endsAt).toLocaleDateString() : '-'}</span></div>
        </Card>
      </div>

      <div className="mt-6">
        <Link to="/tournaments/new">
          <Button variant="primary" size="md">{t('tournament.create')}</Button>
        </Link>
      </div>
    </div>
  )
}
