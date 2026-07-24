import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useTournaments } from '../hooks/useTournament'
import { useOrgContext } from '../hooks/useOrgContext'
import { Button, Card, Badge } from '../components/ui'

export default function ListTournamentsPage() {
  const { t } = useTranslation()
  const { activeOrgId } = useOrgContext()
  const { data: tournaments, isLoading } = useTournaments(activeOrgId)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <p className="text-fg-muted">{t('common.loading')}</p>
      </div>
    )
  }

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

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-heading text-2xl text-fg">{t('nav.tournaments')}</h1>
        <Link to="/tournaments/new">
          <Button variant="primary" size="md">
            {t('tournament.create')}
          </Button>
        </Link>
      </div>

      {(!tournaments || tournaments.length === 0) ? (
        <div className="flex flex-col items-center justify-center min-h-[40vh] text-center">
          <p className="text-fg-muted mb-4">No tournaments yet. Create your first tournament.</p>
          <Link to="/tournaments/new">
            <Button variant="primary" size="md">
              {t('tournament.create')}
            </Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {tournaments.map((tournament) => (
            <Link key={tournament.id} to={`/tournaments/${tournament.id}`}>
              <Card padding="md" className="hover:shadow-md transition-shadow h-full">
                <div className="flex items-start justify-between mb-2">
                  <h2 className="font-heading text-lg text-fg truncate">
                    {tournament.disciplineName || 'Unnamed'}
                  </h2>
                  <Badge variant={stateBadge(tournament.state)}>
                    {tournament.state}
                  </Badge>
                </div>
                <div className="flex items-center gap-2 text-xs text-fg-muted">
                  <span>{tournament.formatType}</span>
                  <span>·</span>
                  <span>{tournament.disciplineName}</span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
