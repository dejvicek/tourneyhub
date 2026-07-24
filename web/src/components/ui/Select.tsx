import { type SelectHTMLAttributes } from 'react'

type SelectProps = {
  label: string
  options: { value: string; label: string }[]
  error?: string
} & SelectHTMLAttributes<HTMLSelectElement>

export default function Select({ label, options, error, className = '', id, ...props }: SelectProps) {
  const selectId = id || label.toLowerCase().replace(/\s+/g, '-')

  return (
    <div className="w-full">
      <label htmlFor={selectId} className="block text-sm font-medium text-fg mb-1">
        {label}
      </label>
      <select
        id={selectId}
        className={`w-full px-3 py-2 rounded-md border bg-bg-surface text-fg text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-offset-bg ${
          error
            ? 'border-accent focus:ring-accent'
            : 'border-border hover:border-border-hover focus:border-primary focus:ring-primary'
        } ${className}`}
        aria-invalid={!!error}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p className="mt-1 text-xs text-accent" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
