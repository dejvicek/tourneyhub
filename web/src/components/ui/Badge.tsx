import { type ReactNode } from 'react'

type BadgeProps = {
  variant: 'default' | 'success' | 'warning' | 'danger' | 'info'
  children: ReactNode
}

const variantClasses: Record<BadgeProps['variant'], string> = {
  default: 'bg-bg-subtle text-fg-muted',
  success: 'bg-primary/15 text-primary',
  warning: 'bg-yellow-500/15 text-yellow-600 dark:text-yellow-400',
  danger: 'bg-accent/15 text-accent',
  info: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
}

export default function Badge({ variant, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${variantClasses[variant]}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-60" />
      {children}
    </span>
  )
}
