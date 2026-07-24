import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useVerifyEmail } from '../../hooks/useAuth'
import { Button, Input } from '../../components/ui'

export default function VerifyEmailPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const verify = useVerifyEmail()
  const [token, setToken] = useState(searchParams.get('token') || '')
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    verify.mutate(
      { token },
      {
        onSuccess: () => navigate('/dashboard'),
        onError: () => setError(t('auth.invalidToken')),
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label={t('auth.tokenPlaceholder')}
        type="text"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        required
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
        loading={verify.isPending}
        className="w-full"
      >
        {t('auth.verifyEmailButton')}
      </Button>
    </form>
  )
}
