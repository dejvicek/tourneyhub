import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useResetPassword } from '../../hooks/useAuth'
import { Button, Input } from '../../components/ui'
import { useToast } from '../../hooks/useToast'

export default function ResetPasswordPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const reset = useResetPassword()
  const { toast } = useToast()
  const resetToken = searchParams.get('token')

  const [email, setEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')

  const handleRequest = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    reset.mutate(
      { email },
      {
        onSuccess: () => toast(t('auth.checkEmail'), 'success'),
        onError: (err: Error) => setError(err.message),
      },
    )
  }

  const handleReset = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    reset.mutate(
      { token: resetToken!, newPassword },
      {
        onSuccess: () => {
          toast(t('auth.resetSuccess'), 'success')
          navigate('/login')
        },
        onError: (err: Error) => setError(err.message),
      },
    )
  }

  const isStep2 = !!resetToken

  return (
    <form onSubmit={isStep2 ? handleReset : handleRequest} className="space-y-4">
      {isStep2 ? (
        <>
          <p className="text-sm text-fg-muted">{t('auth.step2')}</p>
          <Input
            label={t('auth.newPassword')}
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            autoComplete="new-password"
            hint={t('auth.passwordTooShort')}
          />
          <Button
            variant="primary"
            size="md"
            type="submit"
            loading={reset.isPending}
            className="w-full"
          >
            {t('auth.resetButton')}
          </Button>
        </>
      ) : (
        <>
          <p className="text-sm text-fg-muted">{t('auth.step1')}</p>
          <Input
            label={t('auth.email')}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
          {error && (
            <p className="text-xs text-accent" role="alert">
              {error}
            </p>
          )}
          <Button
            variant="primary"
            size="md"
            type="submit"
            loading={reset.isPending}
            className="w-full"
          >
            {t('auth.requestReset')}
          </Button>
        </>
      )}
    </form>
  )
}
