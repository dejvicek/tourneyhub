import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useOrganization, useTransferOwnership } from '../hooks/useOrganization'
import { Button, Card, Modal, Input, Badge } from '../components/ui'

export default function OrgViewPage() {
  const { t } = useTranslation()
  const { orgId } = useParams<{ orgId: string }>()
  const { data: org, isLoading } = useOrganization(orgId!)
  const transferOwnership = useTransferOwnership(orgId!)
  const [transferOpen, setTransferOpen] = useState(false)
  const [newOwnerId, setNewOwnerId] = useState('')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <p className="text-fg-muted">{t('common.loading')}</p>
      </div>
    )
  }

  if (!org) return null

  return (
    <div className="max-w-2xl">
      <h1 className="font-heading text-2xl text-fg mb-6">{org.name}</h1>

      <Card padding="md" className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-fg-muted">{t('org.slug')}</span>
          <span className="text-sm font-mono text-fg">{org.slug}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-fg-muted">Status</span>
          <Badge variant={org.state === 'active' ? 'success' : 'default'}>
            {org.state}
          </Badge>
        </div>
        {org.plan && (
          <div className="flex items-center justify-between">
            <span className="text-sm text-fg-muted">Plan</span>
            <span className="text-sm text-fg">{org.plan}</span>
          </div>
        )}
      </Card>

      <div className="mt-6 flex gap-3">
        <Button
          variant="secondary"
          size="md"
          onClick={() => setTransferOpen(true)}
        >
          {t('org.transferOwnership')}
        </Button>
      </div>

      <Modal
        open={transferOpen}
        onClose={() => setTransferOpen(false)}
        title={t('org.transferOwnership')}
        actions={
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setTransferOpen(false)}
            >
              {t('common.cancel')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={transferOwnership.isPending}
              onClick={() => {
                transferOwnership.mutate(newOwnerId, {
                  onSuccess: () => setTransferOpen(false),
                })
              }}
            >
              {t('common.confirm')}
            </Button>
          </>
        }
      >
        <Input
          label="New owner user ID"
          type="text"
          value={newOwnerId}
          onChange={(e) => setNewOwnerId(e.target.value)}
        />
      </Modal>
    </div>
  )
}
