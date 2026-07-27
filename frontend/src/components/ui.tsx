/**
 * Small shared building blocks and the per-child colour system.
 *
 * Tailwind cannot build class names at runtime, so child accent colours are
 * looked up from a fixed table rather than interpolated.
 */

import type { ReactNode } from 'react'

export interface Theme {
  gradient: string
  solid: string
  soft: string
  softText: string
  border: string
  text: string
  ring: string
}

const THEMES: Record<string, Theme> = {
  orange: {
    gradient: 'from-orange-500 to-amber-500',
    solid: 'bg-orange-500',
    soft: 'bg-orange-50',
    softText: 'text-orange-700',
    border: 'border-orange-200',
    text: 'text-orange-600',
    ring: 'ring-orange-400',
  },
  cyan: {
    gradient: 'from-cyan-500 to-sky-500',
    solid: 'bg-cyan-500',
    soft: 'bg-cyan-50',
    softText: 'text-cyan-700',
    border: 'border-cyan-200',
    text: 'text-cyan-600',
    ring: 'ring-cyan-400',
  },
  violet: {
    gradient: 'from-violet-500 to-purple-500',
    solid: 'bg-violet-500',
    soft: 'bg-violet-50',
    softText: 'text-violet-700',
    border: 'border-violet-200',
    text: 'text-violet-600',
    ring: 'ring-violet-400',
  },
  emerald: {
    gradient: 'from-emerald-500 to-teal-500',
    solid: 'bg-emerald-500',
    soft: 'bg-emerald-50',
    softText: 'text-emerald-700',
    border: 'border-emerald-200',
    text: 'text-emerald-600',
    ring: 'ring-emerald-400',
  },
  rose: {
    gradient: 'from-rose-500 to-pink-500',
    solid: 'bg-rose-500',
    soft: 'bg-rose-50',
    softText: 'text-rose-700',
    border: 'border-rose-200',
    text: 'text-rose-600',
    ring: 'ring-rose-400',
  },
}

export const THEME_NAMES = Object.keys(THEMES)

export function theme(colour?: string | null): Theme {
  return THEMES[colour || 'orange'] || THEMES.orange
}

/** Colour a score by how it compares with the year-group average. */
export function scoreTone(score?: number | null, average?: number | null): string {
  if (score == null) return 'text-slate-400'
  if (average == null) return score >= 70 ? 'text-emerald-600' : 'text-slate-700'
  const gap = score - average
  if (gap >= 0) return 'text-emerald-600'
  if (gap >= -10) return 'text-amber-600'
  return 'text-rose-600'
}

export function Card({
  children,
  className = '',
  padded = true,
}: {
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <div
      className={`rounded-2xl border border-slate-200 bg-white shadow-sm ${
        padded ? 'p-5' : ''
      } ${className}`}
    >
      {children}
    </div>
  )
}

export function SectionTitle({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle?: string
  action?: ReactNode
}) {
  return (
    <div className="mb-3 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function StatTile({
  label,
  value,
  hint,
  tone = 'text-slate-900',
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: string
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${tone}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  )
}

export function Pill({
  children,
  tone = 'slate',
}: {
  children: ReactNode
  tone?: 'slate' | 'green' | 'amber' | 'red' | 'blue' | 'violet'
}) {
  const tones: Record<string, string> = {
    slate: 'bg-slate-100 text-slate-700',
    green: 'bg-emerald-100 text-emerald-700',
    amber: 'bg-amber-100 text-amber-800',
    red: 'bg-rose-100 text-rose-700',
    blue: 'bg-sky-100 text-sky-700',
    violet: 'bg-violet-100 text-violet-700',
  }
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  )
}

export function ProgressBar({
  value,
  max = 100,
  className = 'bg-emerald-500',
}: {
  value: number
  max?: number
  className?: string
}) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
      <div className={`h-full rounded-full transition-all ${className}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function EmptyState({
  icon = '📄',
  title,
  body,
  action,
}: {
  icon?: string
  title: string
  body?: string
  action?: ReactNode
}) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
      <div className="text-4xl">{icon}</div>
      <h3 className="mt-3 font-semibold text-slate-800">{title}</h3>
      {body && <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-12 text-slate-500">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  )
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
      <span>{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 rounded-lg bg-rose-600 px-3 py-1 text-xs font-medium text-white hover:bg-rose-700"
        >
          Try again
        </button>
      )}
    </div>
  )
}

export function Button({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  disabled,
  type = 'button',
  className = '',
  title,
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  type?: 'button' | 'submit'
  className?: string
  title?: string
}) {
  const variants = {
    primary: 'bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-400',
    secondary: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50',
    ghost: 'text-slate-600 hover:bg-slate-100',
    danger: 'bg-rose-600 text-white hover:bg-rose-700',
  }
  const sizes = { sm: 'px-3 py-1.5 text-xs', md: 'px-4 py-2 text-sm', lg: 'px-5 py-2.5 text-base' }

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {children}
    </button>
  )
}

/** Format a due date as friendly relative text. */
export function dueLabel(dueDate?: string | null): { text: string; tone: 'slate' | 'amber' | 'red' | 'green' } {
  if (!dueDate) return { text: 'No date', tone: 'slate' }

  const due = new Date(dueDate)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const dueDay = new Date(due)
  dueDay.setHours(0, 0, 0, 0)

  const days = Math.round((dueDay.getTime() - today.getTime()) / 86_400_000)

  if (days < 0) return { text: days === -1 ? 'Yesterday' : `${Math.abs(days)} days late`, tone: 'red' }
  if (days === 0) return { text: 'Today', tone: 'amber' }
  if (days === 1) return { text: 'Tomorrow', tone: 'amber' }
  if (days <= 7) return { text: due.toLocaleDateString(undefined, { weekday: 'long' }), tone: 'slate' }
  return { text: due.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }), tone: 'slate' }
}

export const SUBJECT_ICONS: Record<string, string> = {
  Mathematics: '📐',
  English: '📖',
  'English Literature': '📚',
  Biology: '🧬',
  Chemistry: '⚗️',
  Physics: '🔭',
  'Combined Science': '🔬',
  PRE: '🧭',
  History: '🏛️',
  Geography: '🌍',
  'Computer Science': '💻',
  Art: '🎨',
  Music: '🎵',
  'Physical Education': '⚽',
  French: '🇫🇷',
  German: '🇩🇪',
  Spanish: '🇪🇸',
  Latin: '🏺',
}

export function subjectIcon(subject: string): string {
  return SUBJECT_ICONS[subject] || '📓'
}
