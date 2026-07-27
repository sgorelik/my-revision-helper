/**
 * Managing students: add, edit, and set the subject baselines the dashboard
 * measures progress against.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { Child, ChildSubject } from '../api/types'
import { useChildren } from '../context/ChildContext'
import {
  Button,
  Card,
  ErrorBanner,
  SectionTitle,
  Spinner,
  THEME_NAMES,
  theme,
} from '../components/ui'

function SubjectEditor({ child }: { child: Child }) {
  const [subjects, setSubjects] = useState<ChildSubject[]>([])
  const [allSubjects, setAllSubjects] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rows, names] = await Promise.all([api.getChildSubjects(child.id), api.getSubjects()])
      setSubjects(rows)
      setAllSubjects(names)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load subjects')
    } finally {
      setLoading(false)
    }
  }, [child.id])

  useEffect(() => {
    void load()
  }, [load])

  const update = (index: number, patch: Partial<ChildSubject>) =>
    setSubjects((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))

  const addRow = () =>
    setSubjects((rows) => [
      ...rows,
      {
        id: `new-${Date.now()}`,
        subject: allSubjects.find((s) => !rows.some((r) => r.subject === s)) || 'Other',
        baselineScore: null,
        yearAverage: null,
        targetScore: null,
        weeklyMinutes: 0,
        priority: 0,
        focusTopics: [],
        reportNotes: null,
      },
    ])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const saved = await api.replaceChildSubjects(
        child.id,
        subjects.map((row) => ({
          subject: row.subject,
          baselineScore: row.baselineScore,
          yearAverage: row.yearAverage,
          targetScore: row.targetScore,
          weeklyMinutes: row.weeklyMinutes || 0,
          priority: row.priority || 0,
          focusTopics: row.focusTopics || [],
          reportNotes: row.reportNotes,
        })),
      )
      setSubjects(saved)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save subjects')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Spinner />

  return (
    <div className="space-y-3">
      {error && <ErrorBanner message={error} />}

      {subjects.length === 0 && (
        <p className="text-sm text-slate-500">
          No subjects yet. Add the ones being revised, with the most recent exam score and the
          year-group average, so progress can be measured against the gap.
        </p>
      )}

      {subjects.map((row, index) => (
        <div key={row.id} className="grid gap-2 rounded-xl bg-slate-50 p-3 sm:grid-cols-12">
          <div className="sm:col-span-4">
            <label className="mb-1 block text-xs text-slate-500">Subject</label>
            <select
              value={row.subject}
              onChange={(e) => update(index, { subject: e.target.value })}
              className="w-full rounded-lg border border-slate-300 p-2 text-sm"
            >
              {Array.from(new Set([...allSubjects, row.subject])).map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="mb-1 block text-xs text-slate-500">Their score</label>
            <input
              type="number"
              value={row.baselineScore ?? ''}
              onChange={(e) =>
                update(index, { baselineScore: e.target.value ? Number(e.target.value) : null })
              }
              className="w-full rounded-lg border border-slate-300 p-2 text-sm"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="mb-1 block text-xs text-slate-500">Year avg</label>
            <input
              type="number"
              value={row.yearAverage ?? ''}
              onChange={(e) =>
                update(index, { yearAverage: e.target.value ? Number(e.target.value) : null })
              }
              className="w-full rounded-lg border border-slate-300 p-2 text-sm"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="mb-1 block text-xs text-slate-500">Min/week</label>
            <input
              type="number"
              value={row.weeklyMinutes || ''}
              onChange={(e) => update(index, { weeklyMinutes: Number(e.target.value) || 0 })}
              className="w-full rounded-lg border border-slate-300 p-2 text-sm"
            />
          </div>
          <div className="flex items-end sm:col-span-2">
            <div className="flex w-full items-center justify-between">
              <span
                className={`text-sm font-semibold ${
                  (row.gap ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'
                }`}
              >
                {row.gap != null ? `${row.gap > 0 ? '+' : ''}${row.gap}` : '—'}
              </span>
              <button
                onClick={() => setSubjects((rows) => rows.filter((_, i) => i !== index))}
                className="rounded p-1 text-slate-400 hover:bg-slate-200"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="sm:col-span-12">
            <label className="mb-1 block text-xs text-slate-500">
              Weak topics from the report (comma separated) — these seed the first practice tests
            </label>
            <input
              value={(row.focusTopics || []).join(', ')}
              onChange={(e) =>
                update(index, {
                  focusTopics: e.target.value
                    .split(',')
                    .map((t) => t.trim())
                    .filter(Boolean),
                })
              }
              placeholder="index laws, expanding brackets, sequences"
              className="w-full rounded-lg border border-slate-300 p-2 text-sm"
            />
          </div>
        </div>
      ))}

      <div className="flex gap-2">
        <Button variant="secondary" size="sm" onClick={addRow}>
          ＋ Add subject
        </Button>
        <Button size="sm" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save subjects'}
        </Button>
      </div>
    </div>
  )
}

export default function ChildrenPage() {
  const { children, reload, loading } = useChildren()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [yearGroup, setYearGroup] = useState('')
  const [colour, setColour] = useState('orange')
  const [emoji, setEmoji] = useState('')
  const [error, setError] = useState<string | null>(null)

  const create = async () => {
    if (!name.trim()) return
    try {
      await api.createChild({
        name: name.trim(),
        yearGroup: yearGroup.trim(),
        colour,
        avatarEmoji: emoji.trim(),
      })
      setName('')
      setYearGroup('')
      setEmoji('')
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add this student')
    }
  }

  const remove = async (child: Child) => {
    if (!confirm(`Remove ${child.name} and all their work? This cannot be undone.`)) return
    try {
      await api.deleteChild(child.id)
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not remove this student')
    }
  }

  if (loading) return <Spinner />

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Students</h1>
        <p className="mt-1 text-slate-600">
          Add each child and record where they currently sit against their year group.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      <section>
        <SectionTitle title="Add a student" />
        <Card>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Yuri"
                className="w-full rounded-xl border border-slate-300 p-2.5 text-sm"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Year group</label>
              <input
                value={yearGroup}
                onChange={(e) => setYearGroup(e.target.value)}
                placeholder="Year 10"
                className="w-full rounded-xl border border-slate-300 p-2.5 text-sm"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Emoji</label>
              <input
                value={emoji}
                onChange={(e) => setEmoji(e.target.value)}
                placeholder="🧪"
                maxLength={4}
                className="w-full rounded-xl border border-slate-300 p-2.5 text-sm"
              />
            </div>
          </div>

          <div className="mt-3">
            <label className="mb-1.5 block text-sm font-medium text-slate-700">Colour</label>
            <div className="flex gap-2">
              {THEME_NAMES.map((name) => (
                <button
                  key={name}
                  onClick={() => setColour(name)}
                  className={`h-8 w-8 rounded-full bg-gradient-to-br ${theme(name).gradient} ${
                    colour === name ? 'ring-2 ring-slate-900 ring-offset-2' : ''
                  }`}
                />
              ))}
            </div>
          </div>

          <div className="mt-4">
            <Button onClick={create} disabled={!name.trim()}>
              Add student
            </Button>
          </div>
        </Card>
      </section>

      <section>
        <SectionTitle title="Existing students" />
        <div className="space-y-3">
          {children.map((child) => {
            const accent = theme(child.colour)
            const isOpen = expanded === child.id
            return (
              <Card key={child.id}>
                <div className="flex items-center gap-4">
                  <span
                    className={`flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br text-lg text-white ${accent.gradient}`}
                  >
                    {child.avatarEmoji || child.name.charAt(0)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-slate-900">{child.name}</div>
                    {child.yearGroup && (
                      <div className="text-sm text-slate-500">{child.yearGroup}</div>
                    )}
                  </div>
                  <Link to={`/dashboard/${child.id}`}>
                    <Button size="sm" variant="secondary">
                      Progress
                    </Button>
                  </Link>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setExpanded(isOpen ? null : child.id)}
                  >
                    {isOpen ? 'Close' : 'Subjects'}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(child)}>
                    🗑
                  </Button>
                </div>

                {isOpen && (
                  <div className="mt-4 border-t border-slate-100 pt-4">
                    <SubjectEditor child={child} />
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      </section>
    </div>
  )
}
