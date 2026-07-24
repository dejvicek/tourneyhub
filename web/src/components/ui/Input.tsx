import { type InputHTMLAttributes } from 'react'

type InputProps = {
  label: string
  error?: string
  hint?: string
} & InputHTMLAttributes<HTMLInputElement>

export default function Input({ label, error, hint, className = '', id, ...props }: InputProps) {
  const inputId = id || label.toLowerCase().replace(/\s+/g, '-')

  return (
    <div className="w-full">
      <label htmlFor={inputId} className="block text-sm font-medium text-fg mb-1">
        {label}
      </label>
      <input
        id={inputId}
        className={`w-full px-3 py-2 rounded-md border bg-bg-surface text-fg placeholder:text-fg-muted text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-offset-bg ${
          error
            ? 'border-accent focus:ring-accent'
            : 'border-border hover:border-border-hover focus:border-primary focus:ring-primary'
        } ${className}`}
        aria-invalid={!!error}
        aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
        {...props}
      />
      {error && (
        <p id={`${inputId}-error`} className="mt-1 text-xs text-accent" role="alert">
          {error}
        </p>
      )}
      {!error && hint && (
        <p id={`${inputId}-hint`} className="mt-1 text-xs text-fg-muted">
          {hint}
        </p>
      )}
    </div>
  )
}
