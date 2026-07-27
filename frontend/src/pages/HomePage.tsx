/**
 * The front door: pick a student, or set the first one up.
 */

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { ChildProgress } from '../api/types'
import { useChildren } from '../context/ChildContext'
import { Button, Card, ErrorBanner, Spinner, theme } from '../components/ui'

function ChildCard({ childId }: { childId: string }) {
  const [progress, setProgress] = useState<ChildProgress | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .getProgress(childId)
      .then((data) => {
        if (!cancelled) setProgress(data)
      })
      .catch(() => {
        // A failed summary should not stop the child being selectable.
      })
    return () => {
      cancelled = true
    }
  }, [childId])

  if (!progress) {
    return (
      <Card className="h-48 animate-pulse bg-slate-50">
        <span className="sr-only">Loading</span>
      </Card>
    )
  }

  const { child } = progress
  const accent = theme(child.colour)
  const outstanding = progress.assignmentsTotal - progress.assignmentsDone

  return (
    <Link to={`/kid/${child.id}`}>
      <Card className="h-full transition-all hover:-translate-y-0.5 hover:shadow-lg">
        <div className="flex items-center gap-4">
          <span
            className={`flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br text-2xl text-white ${accent.gradient}`}
          >
            {child.avatarEmoji || child.name.charAt(0)}
          </span>
          <div className="min-w-0">
            <div className="truncate text-xl font-bold text-slate-900">{child.name}</div>
            {child.yearGroup && <div className="text-sm text-slate-500">{child.yearGroup}</div>}
          </div>
        </div>

        <div className="mt-5 grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-xl font-bold text-slate-900">{outstanding}</div>
            <div className="text-xs text-slate-500">to do</div>
          </div>
          <div>
            <div className="text-xl font-bold text-slate-900">
              {progress.averagePercentage != null
                ? `${Math.round(progress.averagePercentage)}%`
                : '—'}
            </div>
            <div className="text-xs text-slate-500">average</div>
          </div>
          <div>
            <div className="text-xl font-bold text-slate-900">{progress.streakDays}</div>
            <div className="text-xs text-slate-500">day streak</div>
          </div>
        </div>

        {progress.upNext.length > 0 && (
          <div className="mt-4 border-t border-slate-100 pt-3">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Next up
            </div>
            <div className="mt-1 truncate text-sm text-slate-700">{progress.upNext[0].title}</div>
          </div>
        )}
      </Card>
    </Link>
  )
}

export default function HomePage() {
  const { children, loading, error, reload } = useChildren()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [yearGroup, setYearGroup] = useState('')
  const [creating, setCreating] = useState(false)

  const createChild = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      const child = await api.createChild({ name: name.trim(), yearGroup: yearGroup.trim() })
      await reload()
      navigate(`/kid/${child.id}`)
    } finally {
      setCreating(false)
    }
  }

  if (loading) return <Spinner label="Loading…" />

  return (
    <div className="space-y-8">
      {error && <ErrorBanner message={error} onRetry={reload} />}

      {children.length === 0 ? (
        <div className="mx-auto max-w-lg">
          <div className="mb-8 text-center">
            <div className="text-5xl">🎯</div>
            <h1 className="mt-4 text-3xl font-bold text-slate-900">Set up your first student</h1>
            <p className="mt-2 text-slate-600">
              Add a child, upload their papers, and track how they're going against their year
              group.
            </p>
          </div>

          <Card className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && createChild()}
                placeholder="Yuri"
                className="w-full rounded-xl border border-slate-300 p-2.5 focus:border-slate-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">
                Year group (optional)
              </label>
              <input
                value={yearGroup}
                onChange={(e) => setYearGroup(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && createChild()}
                placeholder="Year 10"
                className="w-full rounded-xl border border-slate-300 p-2.5 focus:border-slate-500 focus:outline-none"
              />
            </div>
            <Button onClick={createChild} disabled={!name.trim() || creating} className="w-full" size="lg">
              {creating ? 'Creating…' : 'Add student'}
            </Button>
          </Card>

          <p className="mt-4 text-center text-sm text-slate-500">
            Already have a study plan and tracker? Run{' '}
            <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">import_study_plan.py</code>{' '}
            to load everything at once.
          </p>
        </div>
      ) : (
        <>
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Who's studying?</h1>
            <p className="mt-1 text-slate-600">Pick a student to see their work and progress.</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {children.map((child) => (
              <ChildCard key={child.id} childId={child.id} />
            ))}

            <Link to="/manage/children">
              <Card className="flex h-full min-h-[12rem] items-center justify-center border-dashed text-slate-400 transition-colors hover:border-slate-400 hover:text-slate-600">
                <div className="text-center">
                  <div className="text-3xl">＋</div>
                  <div className="mt-1 text-sm font-medium">Add a student</div>
                </div>
              </Card>
            </Link>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Link to="/manage/library">
              <Card className="transition-shadow hover:shadow-md">
                <div className="text-2xl">📚</div>
                <div className="mt-2 font-semibold text-slate-900">Paper library</div>
                <p className="text-sm text-slate-500">
                  Upload workbooks and papers, then assign them.
                </p>
              </Card>
            </Link>
            <Link to="/practice">
              <Card className="transition-shadow hover:shadow-md">
                <div className="text-2xl">✍️</div>
                <div className="mt-2 font-semibold text-slate-900">Quick practice</div>
                <p className="text-sm text-slate-500">
                  Generate questions on any topic, without assigning anything.
                </p>
              </Card>
            </Link>
          </div>
        </>
      )}
    </div>
  )
}
