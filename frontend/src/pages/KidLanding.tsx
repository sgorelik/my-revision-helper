/**
 * A child's home page: how they are doing overall, and what to do next.
 *
 * Written for the student rather than the parent — the framing is
 * encouragement and next actions, not a performance report.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Assignment, ChildProgress, Today } from '../api/types'
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Pill,
  ProgressBar,
  SectionTitle,
  Spinner,
  dueLabel,
  subjectIcon,
  theme,
} from '../components/ui'

/**
 * Today's plan: the blocks and the work in them.
 *
 * Shown above everything else because "what do I do now" is the only question a
 * student has when they sit down. The list is finite on purpose — a day that
 * cannot be finished is a day nobody starts.
 */
function TodayPanel({ today }: { today: Today }) {
  const total = today.dueToday.length + today.overdue.length
  const dayName = new Date(today.date).toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })

  return (
    <section>
      <SectionTitle
        title="Today"
        subtitle={
          total === 0
            ? `${dayName} — nothing set`
            : `${dayName} — ${total} thing${total === 1 ? '' : 's'}` +
              (today.plannedMinutes > 0 ? `, about ${today.plannedMinutes} min planned` : '')
        }
      />

      {today.blocks.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {today.blocks.map((block) => (
            <span
              key={block.blockIndex}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-600"
              title={block.focus || undefined}
            >
              <span>{subjectIcon(block.subject)}</span>
              {block.subject}
              <span className="text-slate-400">{block.plannedMinutes}m</span>
            </span>
          ))}
        </div>
      )}

      {today.overdue.length > 0 && (
        <div className="mb-3 space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-rose-700">
            Catch up first
          </div>
          {today.overdue.map((assignment) => (
            <AssignmentRow key={assignment.id} assignment={assignment} />
          ))}
        </div>
      )}

      {today.dueToday.length > 0 ? (
        <div className="space-y-2">
          {today.dueToday.map((assignment) => (
            <AssignmentRow key={assignment.id} assignment={assignment} />
          ))}
        </div>
      ) : (
        today.overdue.length === 0 && (
          <EmptyState
            icon="☀️"
            title="Nothing set for today"
            body={
              today.upcoming.length > 0
                ? 'Nothing due today. You could get ahead on what is coming up below.'
                : 'Nothing on the list at all. Enjoy it.'
            }
          />
        )
      )}
    </section>
  )
}

function AssignmentRow({ assignment }: { assignment: Assignment }) {
  const due = dueLabel(assignment.dueOn || assignment.dueDate)
  const isTask = assignment.assignmentType === 'task'

  return (
    <Link
      to={`/work/${assignment.id}`}
      className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 transition-shadow hover:shadow-md"
    >
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-xl">
        {subjectIcon(assignment.subject)}
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate font-medium text-slate-900">{assignment.title}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span>{assignment.subject}</span>
          {assignment.estimatedMinutes && <span>· {assignment.estimatedMinutes} min</span>}
          {!isTask && assignment.questionCount > 0 && (
            <span>· {assignment.questionCount} questions</span>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {isTask && <Pill tone="violet">Tick off</Pill>}
        <Pill tone={assignment.isOverdue ? 'red' : due.tone}>{due.text}</Pill>
      </div>
    </Link>
  )
}

export default function KidLanding() {
  const { childId } = useParams<{ childId: string }>()
  const [progress, setProgress] = useState<ChildProgress | null>(null)
  const [todo, setTodo] = useState<Assignment[]>([])
  const [today, setToday] = useState<Today | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!childId) return
    setLoading(true)
    setError(null)
    try {
      const [progressData, todoData, todayData] = await Promise.all([
        api.getProgress(childId),
        api.getTodo(childId),
        api.getToday(childId),
      ])
      setProgress(progressData)
      setTodo(todoData)
      setToday(todayData)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load your work')
    } finally {
      setLoading(false)
    }
  }, [childId])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) return <Spinner label="Loading your work…" />
  if (error) return <ErrorBanner message={error} onRetry={load} />
  if (!progress) return null

  const { child } = progress
  const accent = theme(child.colour)
  const completionPct =
    progress.assignmentsTotal > 0
      ? Math.round((progress.assignmentsDone / progress.assignmentsTotal) * 100)
      : 0

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  // Today's panel already lists these, so the rest of the queue omits them.
  const shownToday = new Set(
    today ? [...today.dueToday, ...today.overdue].map((a) => a.id) : [],
  )
  const laterWork = todo.filter((assignment) => !shownToday.has(assignment.id))

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className={`rounded-3xl bg-gradient-to-br p-6 text-white shadow-lg ${accent.gradient}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-sm/6 opacity-90">{greeting},</div>
            <h1 className="text-3xl font-bold">
              {child.avatarEmoji} {child.name}
            </h1>
            {progress.plan?.summary && (
              <p className="mt-2 max-w-2xl text-sm opacity-90">{progress.plan.summary}</p>
            )}
          </div>

          <div className="flex gap-6 text-center">
            <div>
              <div className="text-3xl font-bold">{progress.streakDays}</div>
              <div className="text-xs opacity-90">day streak</div>
            </div>
            <div>
              <div className="text-3xl font-bold">{completionPct}%</div>
              <div className="text-xs opacity-90">work done</div>
            </div>
            {progress.averagePercentage != null && (
              <div>
                <div className="text-3xl font-bold">{Math.round(progress.averagePercentage)}%</div>
                <div className="text-xs opacity-90">average score</div>
              </div>
            )}
          </div>
        </div>

        {progress.weeklyMinutesTarget > 0 && (
          <div className="mt-5">
            <div className="mb-1 flex justify-between text-xs opacity-90">
              <span>This week's focused time</span>
              <span>
                {progress.minutesLoggedThisWeek} / {progress.weeklyMinutesTarget} min
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-white/30">
              <div
                className="h-full rounded-full bg-white transition-all"
                style={{
                  width: `${Math.min(
                    100,
                    (progress.minutesLoggedThisWeek / progress.weeklyMinutesTarget) * 100,
                  )}%`,
                }}
              />
            </div>
          </div>
        )}
      </div>

      {today && <TodayPanel today={today} />}

      {/* Everything else still outstanding, minus what today already lists. */}
      {laterWork.length > 0 && (
        <section>
          <SectionTitle
            title="Coming up"
            subtitle={`${laterWork.length} more thing${laterWork.length === 1 ? '' : 's'} on the list`}
            action={
              <Link to={`/dashboard/${child.id}`} className="text-sm font-medium text-slate-600 hover:text-slate-900">
                See all progress →
              </Link>
            }
          />
          <div className="space-y-2">
            {laterWork.map((assignment) => (
              <AssignmentRow key={assignment.id} assignment={assignment} />
            ))}
          </div>
        </section>
      )}

      {todo.length === 0 && (
        <EmptyState
          icon="🎉"
          title="Nothing left to do"
          body="Everything assigned has been handed in. Well done."
        />
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Subjects */}
        <section>
          <SectionTitle title="Your subjects" subtitle="How you're tracking against your year group" />
          {progress.subjects.length === 0 ? (
            <EmptyState icon="📚" title="No subjects set up yet" />
          ) : (
            <div className="space-y-2">
              {progress.subjects.map((subject) => {
                const score = subject.latestScore ?? subject.baselineScore
                const gap = subject.gapToAverage ?? subject.baselineGap
                return (
                  <Card key={subject.subject} className="!p-4">
                    <div className="flex items-center gap-3">
                      <span className="text-xl">{subjectIcon(subject.subject)}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="truncate font-medium text-slate-900">
                            {subject.subject}
                          </span>
                          <span className="shrink-0 text-sm font-semibold text-slate-700">
                            {score != null ? `${Math.round(score)}%` : '—'}
                            {subject.yearAverage != null && (
                              <span className="ml-1 text-xs font-normal text-slate-400">
                                vs {Math.round(subject.yearAverage)}%
                              </span>
                            )}
                          </span>
                        </div>
                        <div className="mt-1.5">
                          <ProgressBar
                            value={subject.assignmentsDone}
                            max={Math.max(1, subject.assignmentsTotal)}
                            className={
                              gap == null
                                ? 'bg-slate-400'
                                : gap >= 0
                                  ? 'bg-emerald-500'
                                  : gap >= -10
                                    ? 'bg-amber-500'
                                    : 'bg-rose-500'
                            }
                          />
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {subject.assignmentsDone}/{subject.assignmentsTotal} done
                          {gap != null && (
                            <span className={gap >= 0 ? 'text-emerald-600' : 'text-rose-600'}>
                              {' '}
                              · {gap > 0 ? '+' : ''}
                              {gap} vs year average
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </Card>
                )
              })}
            </div>
          )}
        </section>

        {/* Practice suggestions */}
        <section>
          <SectionTitle
            title="Worth practising"
            subtitle="Topics your marked work says are shaky"
          />
          {progress.weakTopics.length === 0 ? (
            <EmptyState
              icon="✨"
              title="Nothing flagged yet"
              body="Hand in a paper and anything you find hard will show up here, ready to practise."
            />
          ) : (
            <Card>
              <div className="space-y-3">
                {progress.weakTopics.slice(0, 8).map((topic) => (
                  <div key={`${topic.subject}-${topic.topic}`} className="flex items-center gap-3">
                    <span className="text-lg">{subjectIcon(topic.subject)}</span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-slate-800">{topic.topic}</div>
                      <div className="text-xs text-slate-500">{topic.subject}</div>
                    </div>
                    {topic.masteryPct != null && (
                      <span className="shrink-0 text-sm font-semibold text-rose-600">
                        {Math.round(topic.masteryPct)}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
              <div className="mt-4 border-t border-slate-100 pt-4">
                <Link to={`/dashboard/${child.id}`}>
                  <Button variant="secondary" className="w-full">
                    Build a practice test
                  </Button>
                </Link>
              </div>
            </Card>
          )}
        </section>
      </div>

      {/* Recent results */}
      {progress.recentMarkings.length > 0 && (
        <section>
          <SectionTitle title="Recently marked" />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {progress.recentMarkings.map((marking) => (
              <Link key={marking.id} to={`/marking/${marking.id}`}>
                <Card className="transition-shadow hover:shadow-md">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-700">{marking.subject}</span>
                    <span
                      className={`text-2xl font-bold ${
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
                  {marking.marksAvailable != null && (
                    <div className="mt-1 text-xs text-slate-500">
                      {marking.marksAwarded} of {marking.marksAvailable} marks
                    </div>
                  )}
                </Card>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
