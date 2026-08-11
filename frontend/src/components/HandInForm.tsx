/**
 * Handing in work that was never assigned.
 *
 * For work that happened off the plan: a worksheet done on paper, an exercise
 * set in class, a past paper worked through at the table. Either send the scan
 * and have it marked, or record that it was done and type in the score if you
 * marked it yourself.
 *
 * When the answers sit on a separate numbered sheet, either include the
 * question pages earlier in the same upload, or pick the blank library paper
 * the answers belong to.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { HandIn, Paper } from '../api/types'
import { Button, Card, ErrorBanner } from './ui'

const INPUT =
  'w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none'

function today(): string {
  return new Date().toLocaleDateString('en-CA') // ISO-shaped, in local time
}

export default function HandInForm({
  childId,
  onDone,
  audience = 'parent',
}: {
  childId: string
  /** Called once something has been recorded, so the page can refresh. */
  onDone?: () => void
  /** Changes the wording only: a child is handing in, a parent is recording. */
  audience?: 'parent' | 'child'
}) {
  const navigate = useNavigate()

  const [subjects, setSubjects] = useState<string[]>([])
  const [subject, setSubject] = useState('')
  const [title, setTitle] = useState('')
  const [doneOn, setDoneOn] = useState(today())
  const [minutes, setMinutes] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [pastedText, setPastedText] = useState('')
  const [note, setNote] = useState('')
  const [awarded, setAwarded] = useState('')
  const [available, setAvailable] = useState('')
  const [saveToLibrary, setSaveToLibrary] = useState(true)
  const [papers, setPapers] = useState<Paper[]>([])
  const [paperId, setPaperId] = useState('')

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<HandIn | null>(null)

  useEffect(() => {
    api
      .getSubjects()
      .then((names) => {
        setSubjects(names)
        setSubject((current) => current || names[0] || '')
      })
      .catch(() => setSubjects([]))
  }, [])

  useEffect(() => {
    if (!subject) {
      setPapers([])
      setPaperId('')
      return
    }
    api
      .listPapers(subject)
      .then((list) => setPapers(list.items))
      .catch(() => setPapers([]))
    setPaperId('')
  }, [subject])

  const hasWork = files.length > 0 || pastedText.trim().length > 0
  const hasScore = awarded.trim().length > 0
  const linkedPaper = papers.find((p) => p.id === paperId)

  const submit = async () => {
    setError('')
    setResult(null)

    if (!subject) {
      setError('Choose a subject.')
      return
    }
    if (!hasWork && !hasScore && !minutes.trim()) {
      setError('Add the work, the score, or how long it took — otherwise there is nothing to record.')
      return
    }
    if (hasScore && !available.trim()) {
      setError('Say what the work was out of as well, e.g. 18 out of 25.')
      return
    }

    setBusy(true)
    try {
      const handIn = await api.handIn({
        childId,
        subject,
        title: title.trim() || linkedPaper?.title || '',
        note: note.trim(),
        doneOn,
        minutesSpent: minutes.trim() ? Number(minutes) : undefined,
        pastedText: pastedText.trim(),
        marksAwarded: hasScore ? Number(awarded) : undefined,
        marksAvailable: hasScore ? Number(available) : undefined,
        saveToLibrary: paperId ? false : saveToLibrary,
        paperId: paperId || undefined,
        files,
      })

      setResult(handIn)
      setFiles([])
      setPastedText('')
      setTitle('')
      setNote('')
      setAwarded('')
      setAvailable('')
      setMinutes('')
      setPaperId('')
      onDone?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not record this work')
    } finally {
      setBusy(false)
    }
  }

  const busyLabel = hasWork
    ? hasScore
      ? 'Saving the work…'
      : 'Reading and marking the work…'
    : 'Recording…'

  return (
    <Card className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Subject</label>
          <select value={subject} onChange={(e) => setSubject(e.target.value)} className={INPUT}>
            {subjects.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            What was it? (optional)
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Fractions worksheet"
            className={INPUT}
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Day it was done</label>
          <input
            type="date"
            value={doneOn}
            max={today()}
            onChange={(e) => setDoneOn(e.target.value)}
            className={INPUT}
          />
        </div>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-slate-700">
          Photo or scan of the work (optional)
        </label>
        <input
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md,image/*"
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
          className="block w-full cursor-pointer rounded-xl border border-slate-300 p-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:text-white hover:file:bg-slate-800"
        />
        <p className="mt-1.5 text-xs text-slate-500">
          Questions and answers on the same page work as they are. If the answers
          are on a separate numbered sheet, include the question pages earlier in
          the upload, or pick the original paper below.
        </p>
      </div>

      {papers.length > 0 && (
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Original paper from the library (optional)
          </label>
          <select
            value={paperId}
            onChange={(e) => setPaperId(e.target.value)}
            className={INPUT}
          >
            <option value="">Not linked — use questions on the scan</option>
            {papers.map((paper) => (
              <option key={paper.id} value={paper.id}>
                {paper.title}
                {paper.questionCount ? ` (${paper.questionCount} questions)` : ''}
              </option>
            ))}
          </select>
          <p className="mt-1.5 text-xs text-slate-500">
            Needed when you are handing in an answer sheet alone. The numbered
            answers are matched to this paper&apos;s questions.
          </p>
        </div>
      )}

      {files.length > 0 && !paperId && (
        <label className="flex items-start gap-2.5 rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm">
          <input
            type="checkbox"
            checked={saveToLibrary}
            onChange={(e) => setSaveToLibrary(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-slate-300"
          />
          <span>
            <span className="font-medium text-sky-900">Keep the blank paper in the library</span>
            <span className="mt-0.5 block text-xs text-sky-800">
              The answers are stripped out, so the same worksheet can be given to your other child.
            </span>
          </span>
        </label>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Minutes spent (optional)
          </label>
          <input
            type="number"
            min="0"
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            placeholder="45"
            className={INPUT}
          />
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Score, if you marked it yourself (optional)
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min="0"
              value={awarded}
              onChange={(e) => setAwarded(e.target.value)}
              placeholder="18"
              className={INPUT}
            />
            <span className="text-sm text-slate-500">out of</span>
            <input
              type="number"
              min="1"
              value={available}
              onChange={(e) => setAvailable(e.target.value)}
              placeholder="25"
              className={INPUT}
            />
          </div>
          <p className="mt-1.5 text-xs text-slate-500">
            {hasScore
              ? 'Your score is used as it stands — nothing is marked again.'
              : 'Leave empty and a scan will be marked question by question.'}
          </p>
        </div>
      </div>

      <details>
        <summary className="cursor-pointer text-sm font-medium text-slate-600">
          …or type the answers instead of scanning
        </summary>
        <textarea
          value={pastedText}
          onChange={(e) => setPastedText(e.target.value)}
          rows={6}
          placeholder="1. 45&#10;2. £92&#10;3. 3/8"
          className="mt-2 w-full rounded-xl border border-slate-300 p-3 font-mono text-xs focus:border-slate-500 focus:outline-none"
        />
      </details>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-slate-700">Note (optional)</label>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={
            audience === 'child' ? 'Found the last one hard' : 'Rushed it, do this again on Friday'
          }
          className={INPUT}
        />
      </div>

      {error && <ErrorBanner message={error} />}

      {result && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm">
          <div className="font-semibold text-emerald-900">
            Recorded “{result.title}”
            {result.marking?.percentage != null && ` — ${Math.round(result.marking.percentage)}%`}
          </div>
          {result.savedToLibrary && (
            <div className="mt-1 text-emerald-700">
              Kept in the library as a blank worksheet with {result.questionCount} question
              {result.questionCount === 1 ? '' : 's'}, ready to assign again.
            </div>
          )}
          {result.paperId && !result.savedToLibrary && (
            <div className="mt-1 text-emerald-700">
              Marked against the linked library paper
              {result.questionCount ? ` (${result.questionCount} questions)` : ''}.
            </div>
          )}
          {result.marking ? (
            <Button
              variant="secondary"
              size="sm"
              className="mt-2"
              onClick={() => navigate(`/marking/${result.marking!.id}`)}
            >
              See the marking
            </Button>
          ) : (
            <div className="mt-1 text-emerald-700">
              Counted as done. Add a score next time if you want it on the chart.
            </div>
          )}
        </div>
      )}

      <Button onClick={submit} disabled={busy} size="lg" className="w-full">
        {busy ? busyLabel : hasWork ? 'Hand in this work' : 'Record it as done'}
      </Button>
    </Card>
  )
}
