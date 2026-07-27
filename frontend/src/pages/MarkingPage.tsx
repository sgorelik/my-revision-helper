/**
 * Marked work: the score, the per-question breakdown, and the retest button.
 *
 * The expected answer is shown here deliberately — the work is already handed
 * in, so seeing the correct method is the point.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'

import { api } from '../api/client'
import type { Marking, QuestionMark } from '../api/types'
import {
  Button,
  Card,
  ErrorBanner,
  Pill,
  SectionTitle,
  Spinner,
  subjectIcon,
} from '../components/ui'

const VERDICT_STYLE: Record<
  string,
  { label: string; tone: 'green' | 'amber' | 'red' | 'slate'; border: string }
> = {
  correct: { label: 'Full marks', tone: 'green', border: 'border-l-emerald-500' },
  partial: { label: 'Part marks', tone: 'amber', border: 'border-l-amber-500' },
  incorrect: { label: 'Incorrect', tone: 'red', border: 'border-l-rose-500' },
  not_attempted: { label: 'Not attempted', tone: 'slate', border: 'border-l-slate-300' },
}

/**
 * The student's own pages, as they handed them in.
 *
 * A transcript cannot hold a pie chart they drew, and that drawing is often
 * what the marks were for, so the pages themselves are shown next to the marks.
 */
function WorkPages({ submissionId, pageIds }: { submissionId: string; pageIds: string[] }) {
  const [urls, setUrls] = useState<string[]>([])
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (pageIds.length === 0) return
    let live = true
    const created: string[] = []

    void (async () => {
      try {
        for (const pageId of pageIds) {
          const url = await api.submissionPageUrl(submissionId, pageId)
          created.push(url)
          if (!live) break
        }
        if (live) setUrls([...created])
      } catch {
        if (live) setFailed(true)
      }
    })()

    return () => {
      live = false
      created.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [submissionId, pageIds])

  if (pageIds.length === 0 || failed) return null

  const shown = open ? urls : urls.slice(0, 2)

  return (
    <section>
      <SectionTitle
        title="Your work"
        subtitle={`${pageIds.length} page${pageIds.length === 1 ? '' : 's'} exactly as you handed them in`}
        action={
          pageIds.length > 2 ? (
            <Button variant="secondary" onClick={() => setOpen(!open)}>
              {open ? 'Show fewer' : `Show all ${pageIds.length}`}
            </Button>
          ) : undefined
        }
      />
      {urls.length === 0 ? (
        <Spinner label="Loading your pages…" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {shown.map((url, index) => (
            <a key={url} href={url} target="_blank" rel="noreferrer" className="block">
              <img
                src={url}
                alt={`Page ${index + 1} of your work`}
                className="w-full rounded-xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md"
              />
              <div className="mt-1 text-center text-xs text-slate-500">Page {index + 1}</div>
            </a>
          ))}
        </div>
      )}
    </section>
  )
}

function QuestionCard({
  mark,
  markingId,
  onOverride,
}: {
  mark: QuestionMark
  markingId: string
  onOverride: (updated: Marking) => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(String(mark.marksAwarded))
  const [saving, setSaving] = useState(false)

  const style = VERDICT_STYLE[mark.verdict || 'not_attempted'] || VERDICT_STYLE.not_attempted

  const save = async () => {
    setSaving(true)
    try {
      const updated = await api.overrideMark(markingId, mark.id, {
        marksAwarded: Number(value),
      })
      onOverride(updated)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={`rounded-xl border border-l-4 border-slate-200 bg-white p-4 ${style.border}`}>
      <div className="flex items-start gap-3">
        <span className="w-7 shrink-0 pt-0.5 text-sm font-semibold text-slate-400">
          {mark.questionNumber}.
        </span>

        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <p className="whitespace-pre-wrap text-sm text-slate-800">{mark.questionText}</p>
            <div className="flex shrink-0 items-center gap-2">
              <Pill tone={style.tone}>{style.label}</Pill>
              {editing ? (
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    step="0.5"
                    min={0}
                    max={mark.marksAvailable}
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    className="w-16 rounded-lg border border-slate-300 px-2 py-1 text-sm"
                  />
                  <button
                    onClick={save}
                    disabled={saving}
                    className="rounded-lg bg-slate-900 px-2 py-1 text-xs text-white"
                  >
                    {saving ? '…' : 'Save'}
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="px-1 text-xs text-slate-500"
                  >
                    ✕
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setEditing(true)}
                  title="Change this mark"
                  className="rounded-lg px-2 py-1 text-sm font-semibold text-slate-700 hover:bg-slate-100"
                >
                  {mark.marksAwarded}/{mark.marksAvailable}
                </button>
              )}
            </div>
          </div>

          {mark.studentAnswer && (
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Your answer
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{mark.studentAnswer}</p>
            </div>
          )}

          {mark.feedback && (
            <p className="text-sm text-slate-700">
              <span className="font-medium">Examiner: </span>
              {mark.feedback}
            </p>
          )}

          {mark.expectedAnswer && mark.verdict !== 'correct' && (
            <details className="group">
              <summary className="cursor-pointer text-sm font-medium text-sky-700 hover:underline">
                Show the worked answer
              </summary>
              <p className="mt-2 whitespace-pre-wrap rounded-lg bg-sky-50 p-3 text-sm text-slate-700">
                {mark.expectedAnswer}
              </p>
            </details>
          )}

          {mark.topic && <div className="text-xs text-slate-400">Topic: {mark.topic}</div>}
        </div>
      </div>
    </div>
  )
}

export default function MarkingPage() {
  const { markingId } = useParams<{ markingId: string }>()
  const navigate = useNavigate()

  const [marking, setMarking] = useState<Marking | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [buildingRetest, setBuildingRetest] = useState(false)
  const [filter, setFilter] = useState<'all' | 'lost'>('all')

  const load = useCallback(async () => {
    if (!markingId) return
    setLoading(true)
    setError(null)
    try {
      setMarking(await api.getMarking(markingId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load this marking')
    } finally {
      setLoading(false)
    }
  }, [markingId])

  useEffect(() => {
    void load()
  }, [load])

  const buildRetest = async () => {
    if (!marking) return
    setBuildingRetest(true)
    try {
      const retest = await api.createRetest(marking.childId, { markingId: marking.id })
      // The revision is created here; the existing practice flow runs it.
      navigate(`/practice?revisionId=${retest.revisionId}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not build a practice test')
    } finally {
      setBuildingRetest(false)
    }
  }

  if (loading) return <Spinner label="Loading your marks…" />
  if (error) return <ErrorBanner message={error} onRetry={load} />
  if (!marking) return null

  const pct = marking.percentage ?? 0
  const tone = pct >= 70 ? 'emerald' : pct >= 50 ? 'amber' : 'rose'
  const lostMarks = marking.questionMarks.filter((m) => m.verdict !== 'correct')
  const shown = filter === 'lost' ? lostMarks : marking.questionMarks

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link
        to={`/kid/${marking.childId}`}
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"
      >
        ← Back to my work
      </Link>

      {/* Score */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100 text-3xl">
              {subjectIcon(marking.subject)}
            </div>
            <div>
              <div className="text-sm text-slate-500">{marking.subject}</div>
              <div className={`text-4xl font-bold text-${tone}-600`}>{Math.round(pct)}%</div>
              <div className="text-sm text-slate-500">
                {marking.marksAwarded} of {marking.marksAvailable} marks
                {marking.markedBy === 'parent' && ' · adjusted by parent'}
              </div>
              {marking.minutesSpent != null && (
                <div className="text-sm text-slate-500">
                  {marking.timed ? 'Timed' : 'Logged'}: {marking.minutesSpent} min
                  {marking.pauseCount > 0 &&
                    ` · ${marking.pauseCount} pause${marking.pauseCount === 1 ? '' : 's'}`}
                </div>
              )}
            </div>
          </div>

          <Button onClick={buildRetest} disabled={buildingRetest} size="lg">
            {buildingRetest ? 'Building…' : '🎯 Practise what I got wrong'}
          </Button>
        </div>
      </Card>

      {/* Overall feedback */}
      {marking.overallFeedback && (
        <Card>
          <div className="prose prose-sm max-w-none prose-p:text-slate-700">
            <ReactMarkdown>{marking.overallFeedback}</ReactMarkdown>
          </div>
        </Card>
      )}

      <WorkPages submissionId={marking.submissionId} pageIds={marking.pageImageIds || []} />

      {marking.weakTopics.length > 0 && (
        <Card className="border-amber-200 bg-amber-50">
          <div className="text-sm font-semibold text-amber-900">Topics to go back over</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {marking.weakTopics.map((topic) => (
              <span
                key={topic}
                className="rounded-full bg-white px-3 py-1 text-sm font-medium text-amber-800 shadow-sm"
              >
                {topic}
              </span>
            ))}
          </div>
        </Card>
      )}

      {/* Per-question */}
      {marking.questionMarks.length > 0 && (
        <section>
          <SectionTitle
            title="Question by question"
            subtitle="Tap a mark to change it if the marking got something wrong"
            action={
              <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
                <button
                  onClick={() => setFilter('all')}
                  className={`rounded px-3 py-1 text-xs font-medium ${
                    filter === 'all' ? 'bg-white shadow-sm' : 'text-slate-600'
                  }`}
                >
                  All {marking.questionMarks.length}
                </button>
                <button
                  onClick={() => setFilter('lost')}
                  className={`rounded px-3 py-1 text-xs font-medium ${
                    filter === 'lost' ? 'bg-white shadow-sm' : 'text-slate-600'
                  }`}
                >
                  Lost marks {lostMarks.length}
                </button>
              </div>
            }
          />
          <div className="space-y-2">
            {shown.map((mark) => (
              <QuestionCard
                key={mark.id}
                mark={mark}
                markingId={marking.id}
                onOverride={setMarking}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
