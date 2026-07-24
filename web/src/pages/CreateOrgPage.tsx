import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useCreateOrganization } from '../hooks/useOrganization'
import { useOrgContext } from '../hooks/useOrgContext'
import { Button, Input } from '../components/ui'

export default function CreateOrgPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const createOrg = useCreateOrganization()
  const { setActiveOrgId } = useOrgContext()
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [error, setError] = useState('')

  const generateSlug = (value: string): string => {
    return value
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .slice(0, 50)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    createOrg.mutate(
      { name, slug: slug || undefined },
      {
        onSuccess: (data: unknown) => {
          const org = data as { id: string }
          setActiveOrgId(org.id)
          navigate('/dashboard')
        },
        onError: (err: Error) => setError(err.message),
      },
    )
  }

  return (
    <div className="max-w-md mx-auto">
      <h1 className="font-heading text-2xl text-fg mb-6">{t('org.create')}</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label={t('org.name')}
          type="text"
          value={name}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
            setName(e.target.value)
            if (!slug || slug === generateSlug(name)) {
              setSlug(generateSlug(e.target.value))
            }
          }}
          required
        />
        <Input
          label={t('org.slug')}
          type="text"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          hint="lowercase, numbers, hyphens — 3-50 characters"
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
          loading={createOrg.isPending}
          className="w-full"
        >
          {t('org.createButton')}
        </Button>
      </form>
    </div>
  )
}
