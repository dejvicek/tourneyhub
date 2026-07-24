import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useRegister } from '../../hooks/useAuth'
import { Button, Input } from '../../components/ui'

export default function RegisterPage() {
  const { t } = useTranslation()
  const register = useRegister()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const passwordStrength = () => {
    if (password.length < 12) return { level: 0, label: t('auth.passwordTooShort') }
    if (password.length < 14) return { level: 1, label: t('auth.passwordWeak') }
    if (password.length < 12 || !/[A-Z]/.test(password) || !/[0-9]/.test(password))
      return { level: 2, label: t('auth.passwordGood') }
    return { level: 3, label: t('auth.passwordStrong') }
  }

  const strength = passwordStrength()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    register.mutate(
      { email, password, displayName: displayName || undefined, consentPolicyVersion: '1.0' },
      {
        onSuccess: () => setSuccess(true),
        onError: (err: Error) => setError(err.message),
      },
    )
  }

  if (success) {
    return (
      <div className="text-center space-y-4">
        <p className="text-fg text-sm">{t('auth.checkEmail')}</p>
        <Link to="/verify-email" className="text-primary hover:underline text-sm">
          {t('auth.verifyEmail')}
        </Link>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label={t('auth.email')}
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        autoComplete="email"
      />
      <Input
        label={t('auth.displayName')}
        type="text"
        value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
        autoComplete="name"
      />
      <div>
        <Input
          label={t('auth.password')}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="new-password"
        />
        {password.length > 0 && (
          <div className="mt-2">
            <div className="flex gap-1 mb-1">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className={`h-1 flex-1 rounded-full transition-colors ${
                    i <= strength.level
                      ? strength.level <= 1
                        ? 'bg-accent'
                        : strength.level === 2
                          ? 'bg-yellow-500'
                          : 'bg-primary'
                      : 'bg-bg-subtle'
                  }`}
                />
              ))}
            </div>
            <p className="text-xs text-fg-muted">
              {t('auth.passwordStrength')}: {strength.label}
            </p>
          </div>
        )}
      </div>
      <label className="flex items-start gap-2 text-sm text-fg-muted cursor-pointer">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          className="mt-0.5 accent-primary"
          required
        />
        <span>{t('auth.consentPolicy')}</span>
      </label>
      {error && (
        <p className="text-xs text-accent" role="alert">
          {error}
        </p>
      )}
      <Button
        variant="primary"
        size="md"
        type="submit"
        loading={register.isPending}
        className="w-full"
      >
        {t('auth.registerButton')}
      </Button>
      <p className="text-center text-sm text-fg-muted">
        {t('auth.alreadyHaveAccount')}{' '}
        <Link to="/login" className="text-primary hover:underline">
          {t('auth.login')}
        </Link>
      </p>
    </form>
  )
}
