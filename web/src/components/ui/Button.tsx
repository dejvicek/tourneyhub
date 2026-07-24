import { type ButtonHTMLAttributes, type ReactNode } from 'react'

type ButtonProps = {
  variant: 'primary' | 'secondary' | 'danger' | 'ghost'
  size: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  children: ReactNode
} & ButtonHTMLAttributes<HTMLButtonElement>

const variantClasses: Record<ButtonProps['variant'], string> = {
  primary:
    'bg-primary text-primary-fg hover:bg-primary-hover focus-visible:ring-primary',
  secondary:
    'border border-border hover:border-border-hover text-fg hover:bg-bg-subtle focus-visible:ring-border-hover',
  danger:
    'bg-accent text-white hover:opacity-90 focus-visible:ring-accent',
  ghost:
    'text-fg-muted hover:text-fg hover:bg-bg-subtle focus-visible:ring-border',
}

const sizeClasses: Record<ButtonProps['size'], string> = {
  sm: 'px-3 py-1.5 text-sm rounded',
  md: 'px-4 py-2 text-sm rounded-md',
  lg: 'px-6 py-3 text-base rounded-md',
}

export default function Button({
  variant,
  size,
  loading = false,
  disabled,
  children,
  className = '',
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-50 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg
          className="animate-spin h-4 w-4"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
      )}
      {children}
    </button>
  )
}
