/**
 * Doing a piece of work: read the questions, then hand it in.
 *
 * For a paper this shows the questions (never the answers) and takes photos or
 * typed answers for marking. For a checkable task it just confirms it was done
 * and records the time.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { Assignment, Paper, ResourceLink } from '../api/types'
import {
  Button,
  Card,
  ErrorBanner,
  Pill,
  SectionTitle,
  Spinner,
  dueLabel,
  subjectIcon,
} from '../components/ui'

const KIND_LABELS: Record<string, { icon: string; verb: string }> = {
  watch: { icon: '▶', verb: 'Watch' },
  read: { icon: '📖', verb: 'Read' },
  practise: { icon: '✏️', verb: 'Practise' },
}

/**
 * The "watch this first" links.
 *
 * Kept above the questions and left there for the whole task rather than being
 * dismissed once work starts: the common case is getting stuck halfway and
 * wanting the explanation again.
 */
function ResourceLinks({ resources }: { resources: ResourceLink[] }) {
  if (resources.length === 0) return null

  return (
    <Card className="border-sky-200 bg-sky-50">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-sky-900">
        Before you start
      </h2>
      <div className="mt-3 space-y-2">
        {resources.map((resource) => {
          const kind = KIND_LABELS[resource.kind] || KIND_LABELS.watch
          return (
            <a
              key={resource.url}
              href={resource.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-3 rounded-xl border border-sky-200 bg-white p-3 transition hover:border-sky-400 hover:shadow-sm"
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-sky-100 text-sky-700">
                {kind.icon}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold text-slate-900">
                  {resource.label || `${kind.verb} this first`}
                </span>
                <span className="block truncate text-xs text-slate-500">{resource.url}</span>
              </span>
              <span className="shrink-0 text-sky-600">→</span>
            </a>
          )
        })}
      </div>
      <p className="mt-3 text-xs text-sky-800">
        These stay here while you work — come back any time you get stuck. They are also printed
        on your worksheet with a QR code.
      </p>
    </Card>
  )
}

function clockFace(totalSeconds: number) {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(rest)}` : `${minutes}:${pad(rest)}`
}

/**
 * Start, pause and finish a sitting, so nobody has to estimate minutes.
 *
 * The server owns the time. The display ticks locally between requests, but it
 * counts forward from the elapsed total the server last reported rather than
 * from a start timestamp, because the device's own clock may be wrong and every
 * refresh has to agree with what will actually be recorded.
 */
function TestTimer({
  assignment,
  onChange,
}: {
  assignment: Assignment
  onChange: (updated: Assignment) => void
}) {
  const { timer } = assignment
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // The server's total, and the local moment it arrived.
  const [anchor, setAnchor] = useState({ seconds: timer.elapsedSeconds, at: Date.now() })
  const [shown, setShown] = useState(timer.elapsedSeconds)

  useEffect(() => {
    setAnchor({ seconds: timer.elapsedSeconds, at: Date.now() })
    setShown(timer.elapsedSeconds)
  }, [timer.elapsedSeconds, timer.state])

  useEffect(() => {
    if (timer.state !== 'running') return
    const tick = window.setInterval(() => {
      setShown(anchor.seconds + Math.round((Date.now() - anchor.at) / 1000))
    }, 1000)
    return () => window.clearInterval(tick)
  }, [timer.state, anchor])

  const act = async (action: 'start' | 'pause' | 'resume' | 'stop' | 'reset') => {
    setBusy(action)
    setError(null)
    try {
      onChange(await api.assignmentTimer(assignment.id, action))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The timer did not respond')
    } finally {
      setBusy(null)
    }
  }

  const running = timer.state === 'running'
  const paused = timer.state === 'paused'
  const finished = timer.state === 'stopped'

  return (
    <Card
      className={
        running
          ? 'border-emerald-300 bg-emerald-50'
          : paused
            ? 'border-amber-300 bg-amber-50'
            : undefined
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {timer.state === 'idle'
              ? 'Time yourself'
              : running
                ? 'Timing now'
                : paused
                  ? 'Paused'
                  : 'Finished'}
          </div>
          <div
            className={`font-mono text-4xl font-bold tabular-nums ${
              running ? 'text-emerald-800' : paused ? 'text-amber-800' : 'text-slate-900'
            }`}
          >
            {clockFace(running ? shown : timer.elapsedSeconds)}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {timer.pauseCount > 0 && (
              <>
                {timer.pauseCount} pause{timer.pauseCount === 1 ? '' : 's'}
                {assignment.estimatedMinutes ? ' · ' : ''}
              </>
            )}
            {assignment.estimatedMinutes ? `${assignment.estimatedMinutes} min expected` : ''}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {timer.state === 'idle' && (
            <Button size="lg" onClick={() => act('start')} disabled={busy !== null}>
              {busy ? 'Starting…' : 'Start test'}
            </Button>
          )}
          {running && (
            <>
              <Button variant="secondary" onClick={() => act('pause')} disabled={busy !== null}>
                Pause
              </Button>
              <Button onClick={() => act('stop')} disabled={busy !== null}>
                Finish test
              </Button>
            </>
          )}
          {paused && (
            <>
              <Button size="lg" onClick={() => act('resume')} disabled={busy !== null}>
                Carry on
              </Button>
              <Button variant="secondary" onClick={() => act('stop')} disabled={busy !== null}>
                Finish test
              </Button>
            </>
          )}
          {finished && (
            <Button variant="secondary" onClick={() => act('reset')} disabled={busy !== null}>
              Time it again
            </Button>
          )}
        </div>
      </div>

      {running && (
        <p className="mt-3 text-xs text-emerald-800">
          The clock keeps running even if you close this page, so pause it if you stop working.
        </p>
      )}
      {paused && (
        <p className="mt-3 text-xs text-amber-800">
          Paused time is not counted. Press carry on when you are back.
        </p>
      )}
      {finished && timer.loggedMinutes != null && (
        <p className="mt-3 text-xs text-slate-600">
          {timer.loggedMinutes} minute{timer.loggedMinutes === 1 ? '' : 's'} will be recorded when
          you hand this in.
        </p>
      )}
      {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
    </Card>
  )
}

const BAND_TONES: Record<string, 'slate' | 'blue' | 'amber' | 'violet'> = {
  'warm-up': 'slate',
  standard: 'blue',
  'exam-style': 'amber',
  stretch: 'violet',
}

function QuestionList({ paper }: { paper: Paper }) {
  const questions = paper.questions || []
  if (questions.length === 0) return null

  // Group by the session heading they were printed under.
  const sessions: { label: string; questions: typeof questions }[] = []
  questions.forEach((question) => {
    const label = question.sessionLabel || 'Questions'
    const last = sessions[sessions.length - 1]
    if (last && last.label === label) last.questions.push(question)
    else sessions.push({ label, questions: [question] })
  })

  return (
    <div className="space-y-6">
      {sessions.map((session) => (
        <div key={session.label}>
          <h3 className="mb-3 font-semibold text-slate-900">{session.label}</h3>
          <div className="space-y-2">
            {session.questions.map((question) => (
              <div
                key={question.id}
                className="flex gap-3 rounded-xl border border-slate-200 bg-white p-4"
              >
                <span className="w-7 shrink-0 text-sm font-semibold text-slate-400">
                  {question.number}.
                </span>
                <div className="min-w-0 flex-1">
                  <p className="whitespace-pre-wrap text-slate-800">{question.questionText}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {question.band && (
                      <Pill tone={BAND_TONES[question.band] || 'slate'}>{question.band}</Pill>
                    )}
                    <span className="text-xs text-slate-400">
                      {question.marks} mark{question.marks === 1 ? '' : 's'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function AssignmentPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>()
  const navigate = useNavigate()
  const fileInput = useRef<HTMLInputElement>(null)

  const [assignment, setAssignment] = useState<Assignment | null>(null)
  const [paper, setPaper] = useState<Paper | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [files, setFiles] = useState<File[]>([])
  const [typedAnswers, setTypedAnswers] = useState('')
  const [minutes, setMinutes] = useState('')
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [printing, setPrinting] = useState(false)

  const load = useCallback(async () => {
    if (!assignmentId) return
    setLoading(true)
    setError(null)
    try {
      const assignmentData = await api.getAssignment(assignmentId)
      setAssignment(assignmentData)
      setMinutes(assignmentData.estimatedMinutes ? String(assignmentData.estimatedMinutes) : '')

      if (assignmentData.paperId) {
        setPaper(await api.getPaper(assignmentData.paperId))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load this work')
    } finally {
      setLoading(false)
    }
  }, [assignmentId])

  useEffect(() => {
    void load()
  }, [load])

  const handlePrint = async () => {
    if (!assignmentId) return
    setPrinting(true)
    setSubmitError(null)
    try {
      await api.openWorksheet(assignmentId)
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Could not open the worksheet')
    } finally {
      setPrinting(false)
    }
  }

  const handleSubmitPaper = async () => {
    if (!assignmentId) return
    if (files.length === 0 && !typedAnswers.trim()) {
      setSubmitError('Add a photo of your work, or type your answers below.')
      return
    }

    setSubmitting(true)
    setSubmitError(null)
    try {
      const marking = await api.submitWork(assignmentId, {
        files,
        pastedText: typedAnswers,
        note,
        minutesSpent: minutes ? Number(minutes) : undefined,
      })
      navigate(`/marking/${marking.id}`)
    } catch (e) {
      setSubmitError(
        e instanceof ApiError ? e.message : 'Something went wrong handing this in. Try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  const handleCompleteTask = async () => {
    if (!assignmentId || !assignment) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await api.completeTask(assignmentId, {
        minutesSpent: minutes ? Number(minutes) : undefined,
        note,
      })
      navigate(`/kid/${assignment.childId}`)
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Could not mark this as done')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <Spinner label="Loading…" />
  if (error) return <ErrorBanner message={error} onRetry={load} />
  if (!assignment) return null

  const due = dueLabel(assignment.dueDate)
  const isTask = assignment.assignmentType === 'task'
  const alreadyMarked = assignment.status === 'marked' && assignment.latestMarking
  // What the clock will record, if it was used at all.
  const timedMinutes = assignment.timer.loggedMinutes ?? null

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link
        to={`/kid/${assignment.childId}`}
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"
      >
        ← Back to my work
      </Link>

      {/* Header */}
      <Card>
        <div className="flex items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-slate-100 text-2xl">
            {subjectIcon(assignment.subject)}
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold text-slate-900">{assignment.title}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Pill>{assignment.subject}</Pill>
              <Pill tone={due.tone}>{due.text}</Pill>
              {assignment.estimatedMinutes && <Pill>{assignment.estimatedMinutes} min</Pill>}
              {paper && paper.questionCount > 0 && <Pill>{paper.questionCount} questions</Pill>}
            </div>
            {assignment.instructions && (
              <p className="mt-3 text-slate-600">{assignment.instructions}</p>
            )}
          </div>
        </div>
      </Card>

      {/* Prerequisites come before everything else, including the questions. */}
      <ResourceLinks resources={assignment.resources || []} />

      {/* The clock sits above the questions: it is the first thing to press. */}
      {!alreadyMarked && <TestTimer assignment={assignment} onChange={setAssignment} />}

      {alreadyMarked && (
        <Card className="border-emerald-200 bg-emerald-50">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="font-semibold text-emerald-900">Already marked</div>
              <div className="text-sm text-emerald-700">
                You scored {Math.round(assignment.latestMarking!.percentage ?? 0)}% on this.
              </div>
            </div>
            <Link to={`/marking/${assignment.latestMarking!.id}`}>
              <Button>See feedback</Button>
            </Link>
          </div>
        </Card>
      )}

      {/* Questions. Shown for any paper: the printable worksheet is built from
          the stripped document text even when nothing could be parsed. */}
      {paper && (
        <section>
          <SectionTitle
            title="The questions"
            subtitle="Work through these on paper, then hand in a photo below"
            action={
              <Button variant="secondary" onClick={handlePrint} disabled={printing}>
                {printing ? 'Preparing…' : 'Print worksheet'}
              </Button>
            }
          />
          {(paper.questions?.length ?? 0) > 0 ? (
            <QuestionList paper={paper} />
          ) : (
            <Card>
              <p className="text-slate-600">
                The questions in this one could not be listed separately. Print the worksheet to
                see it in full.
              </p>
            </Card>
          )}
        </section>
      )}

      {/* Hand in */}
      {!alreadyMarked && (
        <section>
          <SectionTitle
            title={isTask ? 'Mark it done' : 'Hand it in'}
            subtitle={
              isTask
                ? 'Confirm you finished, and log how long it took'
                : 'Photograph your working, or type your answers'
            }
          />

          <Card className="space-y-4">
            {!isTask && (
              <>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    Photos of your work
                  </label>
                  <input
                    ref={fileInput}
                    type="file"
                    multiple
                    accept="image/*,.pdf,.docx"
                    onChange={(e) => setFiles(Array.from(e.target.files || []))}
                    className="block w-full cursor-pointer rounded-xl border border-slate-300 p-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:text-white hover:file:bg-slate-800"
                  />
                  {files.length > 0 && (
                    <p className="mt-1.5 text-xs text-slate-500">
                      {files.length} file{files.length === 1 ? '' : 's'} ready:{' '}
                      {files.map((f) => f.name).join(', ')}
                    </p>
                  )}
                </div>

                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    …or type your answers
                  </label>
                  <textarea
                    value={typedAnswers}
                    onChange={(e) => setTypedAnswers(e.target.value)}
                    rows={8}
                    placeholder={'1. a⁷\n2. x⁵\n3. …'}
                    className="w-full rounded-xl border border-slate-300 p-3 font-mono text-sm focus:border-slate-500 focus:outline-none"
                  />
                  <p className="mt-1 text-xs text-slate-500">
                    Number your answers so each one can be matched to its question.
                  </p>
                </div>
              </>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              {/* Once the clock has been used it is the record, so there is
                  nothing to type and nothing to disagree with. */}
              {timedMinutes != null ? (
                <div>
                  <div className="mb-1.5 block text-sm font-medium text-slate-700">Time taken</div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-2.5 text-sm text-slate-700">
                    {timedMinutes} minute{timedMinutes === 1 ? '' : 's'}
                    {assignment.timer.pauseCount > 0 &&
                      `, ${assignment.timer.pauseCount} pause${
                        assignment.timer.pauseCount === 1 ? '' : 's'
                      }`}
                  </div>
                </div>
              ) : (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    Minutes spent
                  </label>
                  <input
                    type="number"
                    min={0}
                    value={minutes}
                    onChange={(e) => setMinutes(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
                  />
                  <p className="mt-1 text-xs text-slate-500">
                    Or use the timer above instead of guessing.
                  </p>
                </div>
              )}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Anything to flag? (optional)
                </label>
                <input
                  type="text"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Got stuck on question 7"
                  className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
                />
              </div>
            </div>

            {submitError && <ErrorBanner message={submitError} />}

            <Button
              onClick={isTask ? handleCompleteTask : handleSubmitPaper}
              disabled={submitting}
              size="lg"
              className="w-full"
            >
              {submitting
                ? isTask
                  ? 'Saving…'
                  : 'Marking your work — this takes a few seconds…'
                : isTask
                  ? 'Mark as done'
                  : 'Hand in for marking'}
            </Button>
          </Card>
        </section>
      )}
    </div>
  )
}
