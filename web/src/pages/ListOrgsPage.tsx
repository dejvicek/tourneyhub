import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useOrganizations } from '../hooks/useOrganization'
import { useOrgContext } from '../hooks/useOrgContext'
import { Button, Card, Badge } from '../components/ui'

export default function ListOrgsPage() {
  const { t } = useTranslation()
  const { data: orgs, isLoading } = useOrganizations()
  const { setActiveOrgId } = useOrgContext()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <p className="text-fg-muted">{t('common.loading')}</p>
      </div>
    )
  }

  if (!orgs || orgs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] text-center">
        <p className="text-fg-muted mb-2">{t('org.noOrgs')}</p>
        <p className="text-fg-muted text-sm mb-4">{t('org.noOrgsCta')}</p>
        <Link to="/orgs/new">
          <Button variant="primary" size="md">
            {t('org.create')}
          </Button>
        </Link>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-heading text-2xl text-fg">{t('nav.dashboard')}</h1>
        <Link to="/orgs/new">
          <Button variant="primary" size="md">
            {t('org.create')}
          </Button>
        </Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {orgs.map((org) => (
          <Card key={org.id} padding="md" className="hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-2">
              <h2 className="font-heading text-lg text-fg truncate">{org.name}</h2>
              <Badge variant={org.state === 'active' ? 'success' : 'default'}>     {org.state}
              </Badge>
            </div>
            <p className="text-fg-muted text-xs mb-4">{org.slug}</p>
            <Button
              variant="secondary"
              size="sm"
              className="w-full"
              onClick={() => {
                setActiveOrgId(org.id)
              }}
            >
              {t('common.confirm')}
            </Button>
          </Card>
        ))}
      </div>
    </div>
  )
}
