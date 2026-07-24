import { type ReactNode } from 'react'

type CardProps = {
  padding?: 'sm' | 'md' | 'lg'
  children: ReactNode
  className?: string
}

const paddingClasses: Record<NonNullable<CardProps['padding']>, string> = {
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
}

export default function Card({ padding = 'md', children, className = '' }: CardProps) {
  return (
    <div
      className={`bg-bg-surface border border-border rounded-lg shadow-sm ${paddingClasses[padding]} ${className}`}
    >
      {children}
    </div>
  )
}
