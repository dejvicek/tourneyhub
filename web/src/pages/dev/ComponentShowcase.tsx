import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Input, Card, Badge, Select, Table, Modal, Bracket } from '../../components/ui'
import { useToast } from '../../hooks/useToast'

export default function ComponentShowcase() {
  const { t } = useTranslation()
  const [modalOpen, setModalOpen] = useState(false)
  const { toast } = useToast()

  return (
    <div className="max-w-4xl mx-auto space-y-12 py-8">
      <h1 className="font-heading text-3xl text-fg">UI Component Showcase</h1>

      <section className="space-y-4">
        <h2 className="font-heading text-xl text-fg">Buttons</h2>
        <div className="flex flex-wrap gap-3">
          <Button variant="primary" size="md">Primary</Button>
          <Button variant="secondary" size="md">Secondary</Button>
          <Button variant="danger" size="md">Danger</Button>
          <Button variant="ghost" size="md">Ghost</Button>
          <Button variant="primary" size="md" loading>Loading</Button>
          <Button variant="primary" size="md" disabled>Disabled</Button>
        </div>
        <h3 className="font-heading text-sm text-fg-muted mt-4">Sizes</h3>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" size="sm">Small</Button>
          <Button variant="primary" size="md">Medium</Button>
          <Button variant="primary" size="lg">Large</Button>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="font-heading text-xl text-fg">Toast</h2>
        <div className="flex flex-wrap gap-3">
          <Button variant="primary" size="sm" onClick={() => toast('Tournament created!', 'success')}>
            Success
          </Button>
          <Button variant="danger" size="sm" onClick={() => toast('Something went wrong', 'error')}>
            Error
          </Button>
          <Button variant="secondary" size="sm" onClick={() => toast('New update available', 'info')}>
            Info
          </Button>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="font-heading text-xl text-fg">Input</h2>
        <div className="max-w-sm space-y-4">
          <Input label="Email" type="email" placeholder="you@example.com" hint={t('auth.checkEmail')} />
          <Input label="Password" type="password" error={t('auth.passwordTooShort')} />
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="font-heading text-xl text-fg">Select</h2>
        <div className="max-w-sm">
          <Select
            label={t('tournament.format')}
            options={[
              { value: 'single', label: t('tournament.singleElimination') },
              { value: 'roundrobin', label: t('tournament.roundRobin') },
              { value: 'swiss', label: t('tournament.swiss') },
            ]}
          />
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="font-heading text-xl text-fg">Card</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Card padding="md">
            <h3 className="font-heading text-lg text-fg mb-1">Small Card</h3>
            <p className="text-fg-muted text-sm">Padding: md</p>
          </Card>
          <Card padding="lg">
            <h3 className="font-heading text-lg text-fg mb-1">Large Card</h3>
            <p className="text-fg-muted text-sm">Padding: lg</p>
          </Card>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="font-heading text-xl text-fg">Badge</h2>
        <div className="flex flex-wrap gap-3">
          <Badge variant="default">Default</Badge>
          <Badge variant="success">Confirmed</Badge>
          <Badge variant="warning">Pending</Badge>
          <Badge variant="danger">Withdrawn</Badge>
          <Badge variant="info">In Progress</Badge>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="font-heading text-xl text-fg">Table</h2>
        <Table
          columns={[
            { key: 'rank', header: '#', sortable: true },
            { key: 'name', header: 'Player', sortable: true },
            { key: 'wins', header: 'W', sortable: true },
            { key: 'losses', header: 'L', sortable: true },
            { key: 'points', header: 'Pts', sortable: true },
          ]}
          data={[
            { rank: 1, name: 'Alice', wins: 8, losses: 1, points: 24 },
            { rank: 2, name: 'Bob', wins: 6, losses: 3, points: 18 },
            { rank: 3, name: 'Charlie', wins: 5, losses: 4, points: 15 },
          ]}
        />
      </section>

      <section className="space-y-4">
        <h2 className="font-heading text-xl text-fg">Modal</h2>
        <Button variant="primary" size="md" onClick={() => setModalOpen(true)}>
          Open Modal
        </Button>
        <Modal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          title={t('common.confirm')}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setModalOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button variant="primary" size="sm" onClick={() => { toast('Confirmed!', 'success'); setModalOpen(false) }}>
                {t('common.confirm')}
              </Button>
            </>
          }
        >
          <p className="text-fg-muted text-sm">Are you sure you want to proceed?</p>
        </Modal>
      </section>

      <section className="space-y-4">
        <h2 className="font-heading text-xl text-fg">Bracket</h2>
        <Bracket
          rounds={[
            { round: 1, label: `${t('tournament.round')} 1` },
            { round: 2, label: `${t('tournament.round')} 2` },
            { round: 3, label: `${t('tournament.round')} 3` },
          ]}
          matches={[
            { id: 'm1', round: 1, slot: 0, participantA: { id: 'a', name: 'Alice' }, participantB: { id: 'b', name: 'Bob' }, state: 'Completed', winnerId: 'a' },
            { id: 'm2', round: 1, slot: 1, participantA: { id: 'c', name: 'Charlie' }, participantB: { id: 'd', name: 'Diana' }, state: 'Completed', winnerId: 'd' },
            { id: 'm3', round: 2, slot: 0, participantA: { id: 'a', name: 'Alice' }, participantB: { id: 'd', name: 'Diana' }, state: 'Pending', winnerId: null },
            { id: 'm4', round: 3, slot: 0, participantA: null, participantB: null, state: 'Pending', winnerId: null },
          ]}
          onMatchClick={(id) => toast(`Match ${id} clicked`, 'info')}
        />
      </section>
    </div>
  )
}
