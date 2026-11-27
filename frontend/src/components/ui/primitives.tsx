import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { clsx } from '../../lib/format'

export function Panel({
  children,
  className,
  title,
  actions,
}: {
  children: ReactNode
  className?: string
  title?: string
  actions?: ReactNode
}) {
  return (
    <section className={clsx('rounded-lg border border-oq-border bg-oq-panel', className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between border-b border-oq-border px-4 py-3">
          <h2 className="text-sm font-medium text-oq-text">{title}</h2>
          {actions}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Button({
  variant = 'primary',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
}) {
  const styles = {
    primary: 'bg-oq-accent text-white hover:bg-oq-accent-hover disabled:opacity-50',
    secondary: 'bg-oq-elevated text-oq-text border border-oq-border hover:border-oq-accent/50',
    ghost: 'text-oq-secondary hover:text-oq-text hover:bg-oq-elevated',
    danger: 'bg-oq-negative/20 text-oq-negative border border-oq-negative/30',
  }
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed',
        styles[variant],
        className,
      )}
      {...props}
    />
  )
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={clsx(
        'w-full rounded-md border border-oq-border bg-oq-elevated px-3 py-1.5 text-sm text-oq-text outline-none focus:border-oq-accent',
        className,
      )}
      {...props}
    />
  )
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={clsx(
        'w-full rounded-md border border-oq-border bg-oq-elevated px-3 py-1.5 text-sm text-oq-text outline-none focus:border-oq-accent',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  )
}

export function Label({ children }: { children: ReactNode }) {
  return <label className="mb-1 block text-[11px] uppercase tracking-wide text-oq-muted">{children}</label>
}

export function MetricCard({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'neutral' | 'positive' | 'negative'
}) {
  const color =
    tone === 'positive' ? 'text-oq-positive' : tone === 'negative' ? 'text-oq-negative' : 'text-oq-text'
  return (
    <div className="rounded-md border border-oq-border bg-oq-elevated px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-oq-muted">{label}</div>
      <div className={clsx('mt-1 font-mono-num text-base font-semibold', color)}>{value}</div>
    </div>
  )
}

export function Alert({
  children,
  tone = 'warning',
}: {
  children: ReactNode
  tone?: 'warning' | 'error' | 'info'
}) {
  const styles = {
    warning: 'border-oq-warning/40 bg-oq-warning/10 text-oq-warning',
    error: 'border-oq-negative/40 bg-oq-negative/10 text-oq-negative',
    info: 'border-oq-accent/40 bg-oq-accent/10 text-oq-accent-hover',
  }
  return (
    <div className={clsx('rounded-md border px-3 py-2 text-sm', styles[tone])}>{children}</div>
  )
}
