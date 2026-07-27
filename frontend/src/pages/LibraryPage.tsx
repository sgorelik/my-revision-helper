/**
 * The paper library: upload work, see what was parsed out of it, and assign it.
 */

import { useCallback, useEffect, useState } from 'react'

import { api, ApiError } from '../api/client'
import type { Paper, ResourceLink } from '../api/types'
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

/** What we know about one file sitting in the staging list, before upload. */
type StagedFile = {
  file: File
  subject: string
  weekLabel: string
  resourceUrl: string
  status: 'pending' | 'uploading' | 'ok' | 'failed'
  error?: string
  title?: string
  foundLinks?: number
}

/**
 * Guess the subject from a filename in the browser, so the parent sees what will
 * happen before uploading rather than after.
 *
 * The server does this too and its answer is authoritative; this is only to fill
 * the form in. Kept to whole-word matches for the same reason as the server:
 * short aliases would otherwise match almost any filename.
 */
const SUBJECT_HINTS: [RegExp, string][] = [
  [/\b(maths?|mathematics)\b/i, 'Mathematics'],
  [/\benglish\s*(lit|literature)\b/i, 'English Literature'],
  [/\benglish\b/i, 'English'],
  [/\b(bio|biology)\b/i, 'Biology'],
  [/\b(chem|chemistry)\b/i, 'Chemistry'],
  [/\b(phys|physics)\b/i, 'Physics'],
  [/\b(geog|geography)\b/i, 'Geography'],
  [/\b(hist|history)\b/i, 'History'],
  [/\b(pre|rs|re)\b/i, 'PRE'],
  [/\b(cs|computing|computer\s*science)\b/i, 'Computer Science'],
  [/\bfrench\b/i, 'French'],
  [/\bspanish\b/i, 'Spanish'],
  [/\blatin\b/i, 'Latin'],
]

function guessSubject(filename: string): string {
  const stem = filename.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ')
  for (const [pattern, subject] of SUBJECT_HINTS) {
    if (pattern.test(stem)) return subject
  }
  return ''
}

function guessWeek(filename: string): string {
  const match = filename.match(/(?:week|wk)[\s_-]*(\d{1,2})/i)
  return match ? `Week ${Number(match[1])}` : ''
}

/**
 * Upload a folder of workbooks in one go.
 *
 * Each file becomes its own library item. Subject and week are guessed from the
 * filename and shown for correction before uploading, because a term's worth of
 * workbooks is named after them and retyping that is the slow part of setup.
 */
function BulkUploadPanel({ onUploaded }: { onUploaded: () => void }) {
  const [subjects, setSubjects] = useState<string[]>([])
  const [staged, setStaged] = useState<StagedFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getSubjects().then(setSubjects).catch(() => setSubjects([]))
  }, [])

  const stage = (files: File[]) => {
    setError(null)
    setStaged((current) => [
      ...current,
      ...files
        // Dropping the same folder twice should not create duplicates.
        .filter((file) => !current.some((s) => s.file.name === file.name))
        .map((file) => ({
          file,
          subject: guessSubject(file.name),
          weekLabel: guessWeek(file.name),
          resourceUrl: '',
          status: 'pending' as const,
        })),
    ])
  }

  const update = (name: string, patch: Partial<StagedFile>) =>
    setStaged((current) => current.map((s) => (s.file.name === name ? { ...s, ...patch } : s)))

  const uploadAll = async () => {
    const queue = staged.filter((s) => s.status === 'pending' || s.status === 'failed')
    if (queue.length === 0) return

    setUploading(true)
    setError(null)
    setStaged((current) =>
      current.map((s) =>
        queue.some((q) => q.file.name === s.file.name) ? { ...s, status: 'uploading' } : s,
      ),
    )

    try {
      const meta: Record<string, Record<string, string>> = {}
      queue.forEach((s) => {
        meta[s.file.name] = {
          subject: s.subject,
          weekLabel: s.weekLabel,
          resourceUrl: s.resourceUrl,
        }
      })

      const response = await api.bulkUploadPapers({ files: queue.map((s) => s.file), meta })

      response.items.forEach((item) => {
        const patch: Partial<StagedFile> = { status: item.status, error: item.error || undefined }
        // Only echo back what the server resolved. Assigning undefined here would
        // blank the subject on a failed row and leave its select uncontrolled.
        if (item.paper) {
          patch.title = item.paper.title
          patch.subject = item.paper.subject
          patch.foundLinks = item.paper.resources.length
        }
        update(item.filename, patch)
      })
      onUploaded()
    } catch (e) {
      // The request itself failed, so nothing was uploaded; put them back so
      // they can be retried rather than silently vanishing.
      setStaged((current) =>
        current.map((s) => (s.status === 'uploading' ? { ...s, status: 'failed' } : s)),
      )
      setError(e instanceof ApiError ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const pending = staged.filter((s) => s.status === 'pending' || s.status === 'failed').length
  const done = staged.filter((s) => s.status === 'ok').length

  return (
    <Card className="space-y-4">
      <div>
        <label className="mb-1.5 block text-sm font-medium text-slate-700">
          Choose several files
        </label>
        <input
          type="file"
          multiple
          accept=".docx,.pdf,.pptx,.xlsx,.txt,.md,image/*"
          onChange={(e) => {
            stage(Array.from(e.target.files || []))
            e.target.value = ''
          }}
          className="block w-full cursor-pointer rounded-xl border border-slate-300 p-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:text-white hover:file:bg-slate-800"
        />
        <p className="mt-1.5 text-xs text-slate-500">
          Each file becomes its own paper. Subject and week are read from the file name where
          possible — check them below before uploading.
        </p>
      </div>

      {staged.length > 0 && (
        <div className="space-y-2">
          {staged.map((item) => (
            <div
              key={item.file.name}
              className={`rounded-xl border p-3 ${
                item.status === 'ok'
                  ? 'border-emerald-200 bg-emerald-50'
                  : item.status === 'failed'
                    ? 'border-rose-200 bg-rose-50'
                    : 'border-slate-200'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                  {item.file.name}
                </span>
                {item.status === 'ok' && (
                  <span className="text-xs font-medium text-emerald-700">
                    Added
                    {item.foundLinks
                      ? ` · ${item.foundLinks} link${item.foundLinks === 1 ? '' : 's'}`
                      : ''}
                  </span>
                )}
                {item.status === 'uploading' && (
                  <span className="text-xs text-slate-500">Reading…</span>
                )}
                {item.status === 'failed' && (
                  <span className="text-xs font-medium text-rose-700">Failed</span>
                )}
                {item.status !== 'uploading' && (
                  <button
                    onClick={() =>
                      setStaged((current) =>
                        current.filter((s) => s.file.name !== item.file.name),
                      )
                    }
                    className="text-slate-400 hover:text-slate-700"
                    aria-label={`Remove ${item.file.name}`}
                  >
                    ✕
                  </button>
                )}
              </div>

              {item.status !== 'ok' && (
                <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_1fr_2fr]">
                  <select
                    value={item.subject}
                    onChange={(e) => update(item.file.name, { subject: e.target.value })}
                    className={`w-full rounded-lg border p-2 text-xs focus:outline-none ${
                      item.subject ? 'border-slate-300' : 'border-amber-400 bg-amber-50'
                    }`}
                  >
                    <option value="">Subject needed…</option>
                    {subjects.map((name) => (
                      <option key={name}>{name}</option>
                    ))}
                  </select>
                  <input
                    value={item.weekLabel}
                    onChange={(e) => update(item.file.name, { weekLabel: e.target.value })}
                    placeholder="Week"
                    className="w-full rounded-lg border border-slate-300 p-2 text-xs focus:outline-none"
                  />
                  <input
                    value={item.resourceUrl}
                    onChange={(e) => update(item.file.name, { resourceUrl: e.target.value })}
                    placeholder="Watch-first link (optional)"
                    className="w-full rounded-lg border border-slate-300 p-2 text-xs focus:outline-none"
                  />
                </div>
              )}

              {item.error && <p className="mt-2 text-xs text-rose-700">{item.error}</p>}
            </div>
          ))}
        </div>
      )}

      {error && <ErrorBanner message={error} />}

      {staged.length > 0 && (
        <div className="flex items-center gap-3">
          <Button onClick={uploadAll} disabled={uploading || pending === 0} className="flex-1">
            {uploading
              ? 'Reading and parsing…'
              : pending === 0
                ? 'All uploaded'
                : `Upload ${pending} file${pending === 1 ? '' : 's'}`}
          </Button>
          {done > 0 && (
            <Button
              variant="ghost"
              onClick={() => setStaged((current) => current.filter((s) => s.status !== 'ok'))}
            >
              Clear {done} done
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}

function UploadPanel({ onUploaded }: { onUploaded: () => void }) {
  const [subjects, setSubjects] = useState<string[]>([])
  const [subject, setSubject] = useState('Mathematics')
  const [title, setTitle] = useState('')
  const [weekLabel, setWeekLabel] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [pastedText, setPastedText] = useState('')
  const [resourceUrl, setResourceUrl] = useState('')
  const [resourceLabel, setResourceLabel] = useState('')
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
      const paper = await api.uploadPaper({
        subject,
        title,
        weekLabel,
        files,
        pastedText,
        resourceUrl,
        resourceLabel,
      })
      setResult(paper)
      setFiles([])
      setPastedText('')
      setTitle('')
      setResourceUrl('')
      setResourceLabel('')
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

      <div className="rounded-xl border border-sky-200 bg-sky-50 p-3">
        <label className="mb-1.5 block text-sm font-medium text-sky-900">
          Watch-first link (optional)
        </label>
        <div className="grid gap-2 sm:grid-cols-[2fr_1fr]">
          <input
            value={resourceUrl}
            onChange={(e) => setResourceUrl(e.target.value)}
            placeholder="https://www.khanacademy.org/…"
            className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
          />
          <input
            value={resourceLabel}
            onChange={(e) => setResourceLabel(e.target.value)}
            placeholder="Watch this first"
            className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>
        <p className="mt-1.5 text-xs text-sky-800">
          Attached to the paper itself, so it comes along every time this is assigned. Shown above
          the questions and printed on the worksheet with a QR code.
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
          {result.resources.length > 0 && (
            <div className="mt-1 text-emerald-700">
              {result.resources.length} link{result.resources.length === 1 ? '' : 's'} found in the
              document: {result.resources.map((r) => r.label || r.url).join(', ')}
            </div>
          )}
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

/**
 * Add or remove the watch-first links on a paper already in the library.
 *
 * Editing them here rather than per assignment is deliberate: the link belongs
 * to the material, so fixing it once fixes every assignment of it.
 */
function LinksModal({
  paper,
  onClose,
  onSaved,
}: {
  paper: Paper
  onClose: () => void
  onSaved: () => void
}) {
  const [links, setLinks] = useState<ResourceLink[]>(paper.resources || [])
  const [url, setUrl] = useState('')
  const [label, setLabel] = useState('')
  const [saving, setSaving] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const scan = async () => {
    setScanning(true)
    setError(null)
    setNotice(null)
    try {
      const updated = await api.extractPaperLinks(paper.id)
      const found = updated.resources.length - links.length
      setLinks(updated.resources)
      setNotice(
        found > 0
          ? `Found ${found} link${found === 1 ? '' : 's'} in the document.`
          : 'No new links in this document.',
      )
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not scan the document')
    } finally {
      setScanning(false)
    }
  }

  const add = () => {
    const trimmed = url.trim()
    if (!trimmed) return
    if (!/^https?:\/\//i.test(trimmed)) {
      setError('Links need to start with http:// or https://')
      return
    }
    setError(null)
    setLinks((current) => [...current, { url: trimmed, label: label.trim() || null, kind: 'watch' }])
    setUrl('')
    setLabel('')
  }

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.updatePaper(paper.id, { resources: links })
      onSaved()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the links')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <Card className="w-full max-w-lg">
        <h3 className="text-lg font-semibold text-slate-900">Links for “{paper.title}”</h3>
        <p className="mt-1 text-sm text-slate-500">
          Shown above the questions and printed on the worksheet with a QR code.
        </p>

        {paper.sourceFileId && (
          <div className="mt-3 flex items-center gap-3 rounded-xl bg-slate-50 p-3">
            <Button size="sm" variant="secondary" onClick={scan} disabled={scanning}>
              {scanning ? 'Reading the document…' : 'Find links in the document'}
            </Button>
            <p className="text-xs text-slate-500">
              Word links are hidden behind their text, so they have to be read out of the file.
            </p>
          </div>
        )}

        {notice && <p className="mt-3 text-sm text-emerald-700">{notice}</p>}

        <div className="mt-4 space-y-2">
          {links.length === 0 && (
            <p className="text-sm text-slate-500">No links on this paper yet.</p>
          )}
          {links.map((link, index) => (
            <div
              key={`${link.url}-${index}`}
              className="flex items-center gap-2 rounded-xl border border-slate-200 p-2.5"
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-slate-800">
                  {link.label || 'Watch this first'}
                </div>
                <div className="truncate text-xs text-slate-500">{link.url}</div>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setLinks((c) => c.filter((_, i) => i !== index))}
              >
                ✕
              </Button>
            </div>
          ))}
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-[2fr_1fr]">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.khanacademy.org/…"
            className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
          />
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Watch this first"
            className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>
        <Button size="sm" variant="secondary" onClick={add} className="mt-2">
          Add link
        </Button>

        {error && (
          <div className="mt-3">
            <ErrorBanner message={error} />
          </div>
        )}

        <div className="mt-5 flex gap-2">
          <Button variant="secondary" onClick={onClose} className="flex-1">
            Cancel
          </Button>
          <Button onClick={save} disabled={saving} className="flex-1">
            {saving ? 'Saving…' : 'Save links'}
          </Button>
        </div>
      </Card>
    </div>
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
  const [scheduledDate, setScheduledDate] = useState('')
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
          scheduledDate: scheduledDate || undefined,
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

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">Do it on</label>
            <input
              type="date"
              value={scheduledDate}
              onChange={(e) => setScheduledDate(e.target.value)}
              className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-500">Shows up in their day.</p>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">Due by</label>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="w-full rounded-xl border border-slate-300 p-2.5 text-sm focus:border-slate-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-500">Late after this.</p>
          </div>
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
  const [editingLinks, setEditingLinks] = useState<Paper | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [uploadMode, setUploadMode] = useState<'bulk' | 'single'>('bulk')

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

  const openFile = async (paper: Paper) => {
    try {
      await api.openPaperFile(paper.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not open the file')
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
        <SectionTitle
          title="Add papers"
          subtitle="Upload a whole folder at once, or add one with full control"
          action={
            <div className="flex gap-1 rounded-xl bg-slate-100 p-1">
              <button
                onClick={() => setUploadMode('bulk')}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  uploadMode === 'bulk' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'
                }`}
              >
                Many files
              </button>
              <button
                onClick={() => setUploadMode('single')}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  uploadMode === 'single' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'
                }`}
              >
                One paper
              </button>
            </div>
          }
        />
        {uploadMode === 'bulk' ? (
          <BulkUploadPanel onUploaded={load} />
        ) : (
          <UploadPanel onUploaded={load} />
        )}
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
                  {paper.resources.length > 0 ? (
                    <Pill tone="blue">
                      {paper.resources.length} link{paper.resources.length === 1 ? '' : 's'}
                    </Pill>
                  ) : (
                    paper.sourceFileId && <Pill tone="slate">No links yet</Pill>
                  )}
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
                  <Button size="sm" variant="secondary" onClick={() => setEditingLinks(paper)}>
                    Links
                  </Button>
                  {paper.sourceFileId && (
                    <Button
                      size="sm"
                      variant="secondary"
                      title="The original upload, answer key included. Parent view only."
                      onClick={() => openFile(paper)}
                    >
                      File
                    </Button>
                  )}
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

      {editingLinks && (
        <LinksModal
          paper={editingLinks}
          onClose={() => setEditingLinks(null)}
          onSaved={() => {
            setToast('Links saved')
            void load()
          }}
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
