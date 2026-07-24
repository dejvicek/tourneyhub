import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useLogin } from '../../hooks/useAuth'
import { Button, Input } from '../../components/ui'

export default function LoginPage() {
  const navigate = useNavigate()
  const login = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    login.mutate(
      { email, password },
      {
        onSuccess: () => navigate('/dashboard'),
        onError: (err: Error) => setError(err.message),
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label="Email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
        autoComplete="email"
      />
      <Input
        label="Password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        autoComplete="current-password"
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
        loading={login.isPending}
        className="w-full"
      >
        Log in
      </Button>
      <div className="text-center text-sm text-fg-muted space-y-1">
        <p>
          <Link to="/reset-password" className="text-primary hover:underline">
            Forgot password?
          </Link>
        </p>
        <p>
          Don't have an account?{' '}
          <Link to="/register" className="text-primary hover:underline">
            Create account
          </Link>
        </p>
      </div>
    </form>
  )
}
