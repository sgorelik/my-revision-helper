/**
 * The progress dashboard.
 *
 * Built around the question the tracker spreadsheet was already asking: how
 * far is each subject from the year-group average, and is that gap closing?
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { api } from '../api/client'
import type { ChildProgress, TopicMastery } from '../api/types'
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Pill,
  SectionTitle,
  Spinner,
  StatTile,
  subjectIcon,
  theme,
} from '../components/ui'

function GapChart({ progress }: { progress: ChildProgress }) {
  const data = useMemo(
    () =>
      progress.subjects
        .filter((s) => s.baselineGap != null || s.gapToAverage != null)
        .map((s) => ({
          subject: s.subject.length > 12 ? `${s.subject.slice(0, 11)}…` : s.subject,
          gap: s.gapToAverage ?? s.baselineGap ?? 0,
        }))
        .sort((a, b) => a.gap - b.gap),
    [progress.subjects],
  )

  if (data.length === 0) {
    return <EmptyState icon="📊" title="No baseline scores yet" body="Import a tracker or add scores to see the gap." />
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="subject" tick={{ fontSize: 11 }} interval={0} angle={-25} textAnchor="end" height={60} />
        <YAxis tick={{ fontSize: 11 }} unit="" />
        <Tooltip
          formatter={(value) => {
            const points = Number(value)
            return [`${points > 0 ? '+' : ''}${points} points`, 'vs year average']
          }}
          contentStyle={{ borderRadius: 12, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <ReferenceLine y={0} stroke="#0f172a" strokeWidth={1.5} />
        <Bar dataKey="gap" radius={[4, 4, 4, 4]}>
          {data.map((entry) => (
            <Cell
              key={entry.subject}
              fill={entry.gap >= 0 ? '#10b981' : entry.gap >= -10 ? '#f59e0b' : '#f43f5e'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function ScoreTrend({ progress }: { progress: ChildProgress }) {
  const [subject, setSubject] = useState<string>('all')

  const subjects = useMemo(
    () => Array.from(new Set(progress.scoreLog.map((e) => e.subject))),
    [progress.scoreLog],
  )

  const data = useMemo(() => {
    const entries = progress.scoreLog
      .filter((e) => subject === 'all' || e.subject === subject)
      .filter((e) => e.scorePct != null)

    return entries.map((entry) => ({
      name: entry.label.length > 18 ? `${entry.label.slice(0, 17)}…` : entry.label,
      score: entry.scorePct,
      yearAverage: entry.yearAveragePct,
    }))
  }, [progress.scoreLog, subject])

  if (progress.scoreLog.length === 0) {
    return (
      <EmptyState
        icon="📈"
        title="No scores recorded yet"
        body="Scores appear here as work gets marked, alongside the year-group average."
      />
    )
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1">
        <button
          onClick={() => setSubject('all')}
          className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
            subject === 'all' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'
          }`}
        >
          All
        </button>
        {subjects.map((name) => (
          <button
            key={name}
            onClick={() => setSubject(name)}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
              subject === name ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'
            }`}
          >
            {name}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" height={60} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
          <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #e2e8f0', fontSize: 12 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="score"
            name="Score"
            stroke="#0ea5e9"
            strokeWidth={2.5}
            dot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="yearAverage"
            name="Year average"
            stroke="#94a3b8"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function RetestBuilder({
  childId,
  weakTopics,
}: {
  childId: string
  weakTopics: TopicMastery[]
}) {
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string[]>([])
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const subject = weakTopics.find((t) => selected.includes(t.topic))?.subject

  const toggle = (topic: string) =>
    setSelected((current) =>
      current.includes(topic) ? current.filter((t) => t !== topic) : [...current, topic],
    )

  const build = async () => {
    setBuilding(true)
    setError(null)
    try {
      const retest = await api.createRetest(childId, {
        subject,
        topics: selected,
        questionCount: 8,
      })
      navigate(`/practice?revisionId=${retest.revisionId}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not build the test')
    } finally {
      setBuilding(false)
    }
  }

  if (weakTopics.length === 0) {
    return (
      <EmptyState
        icon="✨"
        title="No weak topics on record"
        body="Once a paper is marked, whatever went badly shows up here ready to retest."
      />
    )
  }

  // Only one subject can be tested at a time, so selecting narrows the list.
  const selectable = subject ? weakTopics.filter((t) => t.subject === subject) : weakTopics

  return (
    <Card>
      <p className="mb-3 text-sm text-slate-600">
        Pick the topics to be tested on. Questions are generated fresh, so they are not the same
        ones that were already got wrong.
      </p>

      <div className="space-y-1.5">
        {selectable.map((topic) => (
          <label
            key={`${topic.subject}-${topic.topic}`}
            className="flex cursor-pointer items-center gap-3 rounded-lg p-2 hover:bg-slate-50"
          >
            <input
              type="checkbox"
              checked={selected.includes(topic.topic)}
              onChange={() => toggle(topic.topic)}
              className="h-4 w-4 rounded border-slate-300"
            />
            <span className="text-lg">{subjectIcon(topic.subject)}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-slate-800">
                {topic.topic}
              </span>
              <span className="block text-xs text-slate-500">{topic.subject}</span>
            </span>
            {topic.masteryPct != null && (
              <span className="text-sm font-semibold text-rose-600">
                {Math.round(topic.masteryPct)}%
              </span>
            )}
          </label>
        ))}
      </div>

      {error && (
        <div className="mt-3">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="mt-4 border-t border-slate-100 pt-4">
        <Button onClick={build} disabled={selected.length === 0 || building} className="w-full">
          {building
            ? 'Building…'
            : selected.length === 0
              ? 'Choose at least one topic'
              : `Build a test on ${selected.length} topic${selected.length === 1 ? '' : 's'}`}
        </Button>
      </div>
    </Card>
  )
}

export default function DashboardPage() {
  const { childId } = useParams<{ childId: string }>()
  const [progress, setProgress] = useState<ChildProgress | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!childId) return
    setLoading(true)
    setError(null)
    try {
      setProgress(await api.getProgress(childId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load progress')
    } finally {
      setLoading(false)
    }
  }, [childId])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) return <Spinner label="Loading progress…" />
  if (error) return <ErrorBanner message={error} onRetry={load} />
  if (!progress) return null

  const { child } = progress
  const accent = theme(child.colour)
  const behind = progress.subjects.filter(
    (s) => (s.gapToAverage ?? s.baselineGap ?? 0) < 0,
  ).length

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span
            className={`flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br text-lg text-white ${accent.gradient}`}
          >
            {child.avatarEmoji || child.name.charAt(0)}
          </span>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{child.name}'s progress</h1>
            {child.yearGroup && <p className="text-sm text-slate-500">{child.yearGroup}</p>}
          </div>
        </div>
        <Link to={`/kid/${child.id}`}>
          <Button variant="secondary">View as {child.name}</Button>
        </Link>
      </div>

      {/* Headline numbers */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Work completed"
          value={`${progress.assignmentsDone}/${progress.assignmentsTotal}`}
          hint={`${progress.assignmentsDueThisWeek} due this week`}
        />
        <StatTile
          label="Average score"
          value={progress.averagePercentage != null ? `${Math.round(progress.averagePercentage)}%` : '—'}
          hint="across all marked work"
          tone={
            (progress.averagePercentage ?? 0) >= 70
              ? 'text-emerald-600'
              : (progress.averagePercentage ?? 0) >= 50
                ? 'text-amber-600'
                : 'text-rose-600'
          }
        />
        <StatTile
          label="Time this week"
          value={`${progress.minutesLoggedThisWeek} min`}
          hint={progress.weeklyMinutesTarget > 0 ? `target ${progress.weeklyMinutesTarget}` : undefined}
        />
        <StatTile
          label="Subjects behind"
          value={behind}
          hint={`of ${progress.subjects.length} tracked`}
          tone={behind > 0 ? 'text-rose-600' : 'text-emerald-600'}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle
            title="Gap to year average"
            subtitle="Negative means behind the year group"
          />
          <GapChart progress={progress} />
        </Card>

        <Card>
          <SectionTitle title="Scores over time" subtitle="Each result against the year average" />
          <ScoreTrend progress={progress} />
        </Card>
      </div>

      {/* Subject table */}
      <section>
        <SectionTitle title="By subject" />
        {progress.subjects.length === 0 ? (
          <EmptyState icon="📚" title="No subjects yet" />
        ) : (
          <Card padded={false}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Subject</th>
                    <th className="px-4 py-3 font-medium">Latest</th>
                    <th className="px-4 py-3 font-medium">Year avg</th>
                    <th className="px-4 py-3 font-medium">Gap</th>
                    <th className="px-4 py-3 font-medium">Work done</th>
                    <th className="px-4 py-3 font-medium">Time</th>
                    <th className="px-4 py-3 font-medium">Weak topics</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {progress.subjects.map((subject) => {
                    const gap = subject.gapToAverage ?? subject.baselineGap
                    const score = subject.latestScore ?? subject.baselineScore
                    return (
                      <tr key={subject.subject} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-medium text-slate-800">
                          <span className="mr-2">{subjectIcon(subject.subject)}</span>
                          {subject.subject}
                        </td>
                        <td className="px-4 py-3">{score != null ? `${Math.round(score)}%` : '—'}</td>
                        <td className="px-4 py-3 text-slate-500">
                          {subject.yearAverage != null ? `${Math.round(subject.yearAverage)}%` : '—'}
                        </td>
                        <td className="px-4 py-3">
                          {gap != null ? (
                            <span
                              className={`font-semibold ${
                                gap >= 0 ? 'text-emerald-600' : gap >= -10 ? 'text-amber-600' : 'text-rose-600'
                              }`}
                            >
                              {gap > 0 ? '+' : ''}
                              {gap}
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-600">
                          {subject.assignmentsDone}/{subject.assignmentsTotal}
                        </td>
                        <td className="px-4 py-3 text-slate-600">{subject.minutesLogged} min</td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {subject.weakTopics.slice(0, 3).map((topic) => (
                              <Pill key={topic} tone="red">
                                {topic}
                              </Pill>
                            ))}
                            {subject.weakTopics.length === 0 && (
                              <span className="text-slate-400">—</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <SectionTitle title="Build a practice test" subtitle="Target the topics that went badly" />
          <RetestBuilder childId={child.id} weakTopics={progress.weakTopics} />
        </section>

        <section>
          <SectionTitle title="Marked work" />
          {progress.recentMarkings.length === 0 ? (
            <EmptyState icon="📝" title="Nothing marked yet" />
          ) : (
            <div className="space-y-2">
              {progress.recentMarkings.map((marking) => (
                <Link key={marking.id} to={`/marking/${marking.id}`}>
                  <Card className="!p-4 transition-shadow hover:shadow-md">
                    <div className="flex items-center gap-3">
                      <span className="text-xl">{subjectIcon(marking.subject)}</span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-slate-800">
                          {marking.assignmentTitle || marking.subject}
                        </div>
                        <div className="text-xs text-slate-500">
                          {marking.markedAt
                            ? new Date(marking.markedAt).toLocaleDateString()
                            : ''}
                          {marking.weakTopics.length > 0 &&
                            ` · weak on ${marking.weakTopics.slice(0, 2).join(', ')}`}
                        </div>
                      </div>
                      <span
                        className={`text-xl font-bold ${
                          (marking.percentage ?? 0) >= 70
                            ? 'text-emerald-600'
                            : (marking.percentage ?? 0) >= 50
                              ? 'text-amber-600'
                              : 'text-rose-600'
                        }`}
                      >
                        {marking.percentage != null ? `${Math.round(marking.percentage)}%` : '—'}
                      </span>
                    </div>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
