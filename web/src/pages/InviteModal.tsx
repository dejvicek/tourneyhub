import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Input, Modal } from '../components/ui'

type Props = {
  open: boolean
  onClose: () => void
  onInvite: (email: string) => void
}

export default function InviteModal({ open, onClose, onInvite }: Props) {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t('league.invite')}
      actions={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant="primary" size="sm" onClick={() => { onInvite(email); setEmail(''); onClose() }}>
            {t('league.invite')}
          </Button>
        </>
      }
    >
      <Input label={t('auth.email')} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
    </Modal>
  )
}
