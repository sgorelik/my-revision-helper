/**
 * The paper library: upload work, see what was parsed out of it, and assign it.
 */

import { useCallback, useEffect, useState } from 'react'

import { api, ApiError } from '../api/client'
import type { Paper } from '../api/types'
import { useChildren } from '../context/ChildContext'
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Pill,
  SectionTitle,
  Spinner,
  subjectIcon,
} from '../components/ui'

function UploadPanel({ onUploaded }: { onUploaded: () => void }) {
  const [subjects, setSubjects] = useState<string[]>([])
  const [subject, setSubject] = useState('Mathematics')
  const [title, setTitle] = useState('')
  const [weekLabel, setWeekLabel] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [pastedText, setPastedText] = useState('')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Paper | null>(null)

  useEffect(() => {
    api.getSubjects().then(setSubjects).catch(() => setSubjects([]))
  }, [])

  const submit = async () => {
    if (files.length === 0 && !pastedText.trim()) {
      setError('Choose a file or paste the paper text.')
      return
    }
    setUploading(true)
    setError(null)
    setResult(null)
    try {
      const paper = await api.uploadPaper({ subject, title, weekLabel, files, pastedText })
      setResult(paper)
      setFiles([])
      setPastedText('')
      setTitle('')
      onUploaded()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <Card className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Subject</label>
          <select
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
          >
            {subjects.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Title (optional)
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Taken from the document"
            className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-slate-700">Week (optional)</label>
          <input
            value={weekLabel}
            onChange={(e) => setWeekLabel(e.target.value)}
            placeholder="Week 1"
            className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-slate-700">Document</label>
        <input
          type="file"
          multiple
          accept=".docx,.pdf,.pptx,.xlsx,.txt,.md,image/*"
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
          className="block w-full cursor-pointer rounded-xl border border-slate-300 p-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:text-white hover:file:bg-slate-800"
        />
        <p className="mt-1.5 text-xs text-slate-500">
          Word, PDF, PowerPoint, spreadsheets or photos. If the document has an answer key at the
          back it is split off automatically and kept hidden from the student.
        </p>
      </div>

      <details>
        <summary className="cursor-pointer text-sm font-medium text-slate-600">
          …or paste the text instead
        </summary>
        <textarea
          value={pastedText}
          onChange={(e) => setPastedText(e.target.value)}
          rows={6}
          className="mt-2 w-full rounded-xl border border-slate-300 p-3 font-mono text-xs focus:border-slate-500 focus:outline-none"
        />
      </details>

      {error && <ErrorBanner message={error} />}

      {result && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm">
          <div className="font-semibold text-emerald-900">Added “{result.title}”</div>
          <div className="mt-1 text-emerald-700">
            {result.questionCount} questions parsed
            {result.totalMarks ? `, ${result.totalMarks} marks` : ''}
            {result.hasAnswerKey
              ? ' · answer key found and hidden from students'
              : ' · no answer key found, so this will be marked on subject knowledge alone'}
          </div>
          {result.parseError && (
            <div className="mt-1 text-amber-700">Note: {result.parseError}</div>
          )}
        </div>
      )}

      <Button onClick={submit} disabled={uploading} size="lg" className="w-full">
        {uploading ? 'Reading and parsing the document…' : 'Add to library'}
      </Button>
    </Card>
  )
}

function AssignModal({
  paper,
  onClose,
  onAssigned,
}: {
  paper: Paper
  onClose: () => void
  onAssigned: () => void
}) {
  const { children } = useChildren()
  const [selected, setSelected] = useState<string[]>([])
  const [dueDate, setDueDate] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const assign = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.bulkAssign(selected, [
        {
          childId: selected[0],
          title: paper.title,
          subject: paper.subject,
          assignmentType: 'paper',
          paperId: paper.id,
          dueDate: dueDate || undefined,
          weekLabel: paper.weekLabel || undefined,
          estimatedMinutes: paper.estimatedMinutes || undefined,
          verification: 'upload',
        },
      ])
      onAssigned()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not assign this paper')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <Card className="w-full max-w-md">
        <h3 className="text-lg font-semibold text-slate-900">Assign “{paper.title}”</h3>
        <p className="mt-1 text-sm text-slate-500">Choose who should do this.</p>

        <div className="mt-4 space-y-1.5">
          {children.map((child) => (
            <label
              key={child.id}
              className="flex cursor-pointer items-center gap-3 rounded-lg p-2 hover:bg-slate-50"
            >
              <input
                type="checkbox"
                checked={selected.includes(child.id)}
                onChange={() =>
                  setSelected((current) =>
                    current.includes(child.id)
                      ? current.filter((id) => id !== child.id)
                      : [...current, child.id],
                  )
                }
                className="h-4 w-4 rounded border-slate-300"
              />
              <span className="text-sm font-medium text-slate-800">{child.name}</span>
              {child.yearGroup && (
                <span className="text-xs text-slate-500">{child.yearGroup}</span>
              )}
            </label>
          ))}
        </div>

        <div className="mt-4">
          <label className="mb-1.5 block text-sm font-medium text-slate-700">
            Due date (optional)
          </label>
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>

        {error && (
          <div className="mt-3">
            <ErrorBanner message={error} />
          </div>
        )}

        <div className="mt-5 flex gap-2">
          <Button variant="secondary" onClick={onClose} className="flex-1">
            Cancel
          </Button>
          <Button onClick={assign} disabled={selected.length === 0 || saving} className="flex-1">
            {saving ? 'Assigning…' : 'Assign'}
          </Button>
        </div>
      </Card>
    </div>
  )
}

export default function LibraryPage() {
  const [papers, setPapers] = useState<Paper[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [assigning, setAssigning] = useState<Paper | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.listPapers()
      setPapers(response.items)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the library')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const remove = async (paper: Paper) => {
    try {
      await api.deletePaper(paper.id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete this paper')
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Paper library</h1>
        <p className="mt-1 text-slate-600">
          Everything that can be assigned. Papers are parsed into questions so they can be marked
          automatically.
        </p>
      </div>

      <section>
        <SectionTitle title="Add a paper" />
        <UploadPanel onUploaded={load} />
      </section>

      <section>
        <SectionTitle
          title="In the library"
          subtitle={papers.length > 0 ? `${papers.length} paper(s)` : undefined}
        />

        {error && <ErrorBanner message={error} onRetry={load} />}

        {loading ? (
          <Spinner />
        ) : papers.length === 0 ? (
          <EmptyState
            icon="📚"
            title="No papers yet"
            body="Upload a workbook above to get started."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {papers.map((paper) => (
              <Card key={paper.id} className="flex flex-col">
                <div className="flex items-start gap-3">
                  <span className="text-2xl">{subjectIcon(paper.subject)}</span>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold leading-tight text-slate-900">{paper.title}</div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {paper.subject}
                      {paper.weekLabel && ` · ${paper.weekLabel}`}
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Pill>{paper.questionCount} questions</Pill>
                  {paper.totalMarks && <Pill>{paper.totalMarks} marks</Pill>}
                  {paper.hasAnswerKey ? (
                    <Pill tone="green">Answer key</Pill>
                  ) : (
                    <Pill tone="amber">No key</Pill>
                  )}
                  {paper.parseStatus === 'failed' && <Pill tone="red">Parse failed</Pill>}
                </div>

                {paper.topics.length > 0 && (
                  <div className="mt-2 text-xs text-slate-500">
                    {paper.topics.slice(0, 3).join(' · ')}
                  </div>
                )}

                <div className="mt-4 flex gap-2 border-t border-slate-100 pt-3">
                  <Button size="sm" onClick={() => setAssigning(paper)} className="flex-1">
                    Assign
                  </Button>
                  <a href={api.paperFileUrl(paper.id)} className="contents">
                    <Button size="sm" variant="secondary">
                      File
                    </Button>
                  </a>
                  <Button size="sm" variant="ghost" onClick={() => remove(paper)}>
                    🗑
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      {assigning && (
        <AssignModal
          paper={assigning}
          onClose={() => setAssigning(null)}
          onAssigned={() => setToast('Assigned')}
        />
      )}

      {toast && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-xl bg-slate-900 px-4 py-2 text-sm text-white shadow-lg"
          onAnimationEnd={() => setToast(null)}
        >
          {toast}
          <button onClick={() => setToast(null)} className="ml-3 opacity-60">
            ✕
          </button>
        </div>
      )}
    </div>
  )
}
