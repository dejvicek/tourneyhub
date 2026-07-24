import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useCreateRegistration } from '../hooks/useRegistration'
import { Button, Input, Modal } from '../components/ui'

type Props = {
  open: boolean
  onClose: () => void
  tournamentId: string
  teamSize: number
}

export default function RegistrationFlow({ open, onClose, tournamentId, teamSize }: Props) {
  const { t } = useTranslation()
  const register = useCreateRegistration(tournamentId)
  const [name, setName] = useState('')
  const [members, setMembers] = useState<string[]>([])
  const [memberInput, setMemberInput] = useState('')

  const addMember = () => {
    if (memberInput.trim()) {
      setMembers((m) => [...m, memberInput.trim()])
      setMemberInput('')
    }
  }

  const handleSubmit = () => {
    register.mutate(
      { participantDisplayName: name, rosterInviteEmails: members.length > 0 ? members : undefined },
      { onSuccess: () => onClose() },
    )
  }

  const rosterIncomplete = teamSize > 1 && members.length + 1 < teamSize

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${t('registration.register')} Tournament`}
      actions={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant="primary" size="sm" loading={register.isPending} onClick={handleSubmit}>
            {t('registration.confirm')}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label={t('registration.playerName')} type="text" value={name} onChange={(e) => setName(e.target.value)} required />
        {teamSize > 1 && (
          <div>
            <p className="text-sm font-medium text-fg mb-2">{t('registration.teamMembers')}</p>
            <div className="flex gap-2">
              <Input label="" type="text" value={memberInput} onChange={(e) => setMemberInput(e.target.value)} placeholder="Email or name" />
              <Button variant="secondary" size="sm" onClick={addMember}>{t('registration.add')}</Button>
            </div>
            {members.length > 0 && (
              <ul className="mt-2 space-y-1">
                {members.map((m, i) => (
                  <li key={i} className="text-sm text-fg-muted">{m}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {rosterIncomplete && (
          <p className="text-xs text-accent">{t('registration.incompleteRoster')}</p>
        )}
      </div>
    </Modal>
  )
}
