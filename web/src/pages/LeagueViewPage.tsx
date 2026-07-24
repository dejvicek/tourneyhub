import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useLeague, useCreateSeason, useInviteUser } from '../hooks/useLeague'
import { Button, Card, Modal, Input, Badge } from '../components/ui'

export default function LeagueViewPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const { data: league, isLoading } = useLeague(id!)
  const createSeason = useCreateSeason(id!)
  const inviteUser = useInviteUser(id!)
  const [tab, setTab] = useState<'seasons' | 'players' | 'settings'>('seasons')
  const [seasonOpen, setSeasonOpen] = useState(false)
  const [seasonName, setSeasonName] = useState('')
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')

  if (isLoading) return <div className="flex items-center justify-center min-h-[40vh]"><p className="text-fg-muted">{t('common.loading')}</p></div>
  if (!league) return null

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-heading text-2xl text-fg">{league.name}</h1>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant={league.state === 'active' ? 'success' : 'default'}>{league.state}</Badge>
            <span className="text-sm text-fg-muted">{t(`league.${league.visibility}`)}</span>
          </div>
        </div>
      </div>

      <div className="flex border-b border-border mb-6">
        {(['seasons', 'players', 'settings'] as const).map((key) => (
          <button key={key} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${tab === key ? 'border-primary text-primary' : 'border-transparent text-fg-muted hover:text-fg'}`} onClick={() => setTab(key)}>
            {t(`league.${key}`)}
          </button>
        ))}
      </div>

      {tab === 'seasons' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading text-lg text-fg">{t('league.seasons')}</h2>
            <Button variant="primary" size="sm" onClick={() => setSeasonOpen(true)}>
              {t('league.startNewSeason')}
            </Button>
          </div>
          <Card padding="md">
            <p className="text-fg-muted text-sm text-center py-8">{t('common.noData')}</p>
          </Card>
        </div>
      )}

      {tab === 'players' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading text-lg text-fg">{t('league.players')}</h2>
            <Button variant="primary" size="sm" onClick={() => setInviteOpen(true)}>
              {t('league.invite')}
            </Button>
          </div>
          <Card padding="md">
            <p className="text-fg-muted text-sm text-center py-8">{t('common.noData')}</p>
          </Card>
        </div>
      )}

      {tab === 'settings' && (
        <Card padding="md" className="max-w-md">
          <div className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-fg-muted">{t('league.name')}</span><span className="text-fg">{league.name}</span></div>
            <div className="flex justify-between"><span className="text-fg-muted">{t('league.visibility')}</span><span className="text-fg">{t(`league.${league.visibility}`)}</span></div>
          </div>
        </Card>
      )}

      {/* Create Season Modal */}
      <Modal open={seasonOpen} onClose={() => setSeasonOpen(false)} title={t('season.create')}
        actions={<>
          <Button variant="ghost" size="sm" onClick={() => setSeasonOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="primary" size="sm" loading={createSeason.isPending} onClick={() => {
            createSeason.mutate({ name: seasonName, startsAt: new Date().toISOString() }, { onSuccess: () => setSeasonOpen(false) })
          }}>{t('common.create')}</Button>
        </>}>
        <Input label={t('season.name')} type="text" value={seasonName} onChange={(e) => setSeasonName(e.target.value)} />
      </Modal>

      {/* Invite Modal */}
      <Modal open={inviteOpen} onClose={() => setInviteOpen(false)} title={t('league.invite')}
        actions={<>
          <Button variant="ghost" size="sm" onClick={() => setInviteOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="primary" size="sm" loading={inviteUser.isPending} onClick={() => {
            inviteUser.mutate({ email: inviteEmail, role: 'member' }, { onSuccess: () => setInviteOpen(false) })
          }}>{t('league.invite')}</Button>
        </>}>
        <Input label={t('auth.email')} type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
      </Modal>
    </div>
  )
}
