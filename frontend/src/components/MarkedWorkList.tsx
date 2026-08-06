/**
 * A child's marked work, with the ability to put it right.
 *
 * Auto-marking a scan of handwriting is a best effort, and when it is wrong the
 * number sits in the average until someone can reach it. So every row here can
 * be corrected in place or taken off the record, and work the app could not
 * score asks to be marked by hand rather than pretending to be a nought.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { Child, WorkItem } from '../api/types'
import { Button, Card, EmptyState, ErrorBanner, Pill, Spinner, subjectIcon } from './ui'

function percentageOf(item: WorkItem): number | null {
  if (item.percentage != null) return item.percentage
  if (item.marksAvailable) return ((item.marksAwarded ?? 0) / item.marksAvailable) * 100
  return null
}

function scoreColour(percentage: number | null): string {
  if (percentage == null) return 'text-slate-400'
  if (percentage >= 70) return 'text-emerald-600'
  if (percentage >= 50) return 'text-amber-600'
  return 'text-rose-600'
}

function dayOf(iso?: string | null): string {
  if (!iso) return ''
  return iso.slice(0, 10)
}

export function MarkedWorkList({
  childId,
  siblings = [],
  onChange,
}: {
  childId: string
  /** Other children, so misfiled work can be sent to the right one. */
  siblings?: Child[]
  /** Called whenever the record changes, so the figures above can be redrawn. */
  onChange?: () => void
}) {
  const [items, setItems] = useState<WorkItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  // Kept so a deletion can be undone without hunting for it again.
  const [justDeleted, setJustDeleted] = useState<WorkItem | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      setItems(await api.listWork(childId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the marked work')
    }
  }, [childId])

  useEffect(() => {
    void load()
  }, [load])

  const refresh = useCallback(async () => {
    await load()
    onChange?.()
  }, [load, onChange])

  const remove = async (item: WorkItem) => {
    setBusy(item.id)
    try {
      await api.deleteWork(item.id)
      setConfirming(null)
      setJustDeleted(item)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not remove that piece of work')
    } finally {
      setBusy(null)
    }
  }

  const undo = async () => {
    if (!justDeleted) return
    setBusy(justDeleted.id)
    try {
      await api.restoreWork(justDeleted.id)
      setJustDeleted(null)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not put that back')
    } finally {
      setBusy(null)
    }
  }

  const needingReview = useMemo(
    () => (items ?? []).filter((i) => i.status === 'needs_review').length,
    [items],
  )

  if (error && !items) return <ErrorBanner message={error} onRetry={() => void load()} />
  if (!items) return <Spinner label="Loading marked work…" />
  if (items.length === 0) return <EmptyState icon="📝" title="Nothing marked yet" />

  return (
    <div className="space-y-2">
      {error && <ErrorBanner message={error} />}

      {needingReview > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {needingReview === 1
            ? '1 piece of work could not be marked automatically.'
            : `${needingReview} pieces of work could not be marked automatically.`}{' '}
          They are not counted in the average until you give them a mark.
        </div>
      )}

      {justDeleted && (
        <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          <span>Removed “{justDeleted.title}”.</span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => void undo()}>
              Undo
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setJustDeleted(null)}>
              Dismiss
            </Button>
          </div>
        </div>
      )}

      {items.map((item) =>
        editing === item.id ? (
          <EditWorkCard
            key={item.id}
            item={item}
            siblings={siblings.filter((c) => c.id !== childId)}
            onCancel={() => setEditing(null)}
            onSaved={async () => {
              setEditing(null)
              await refresh()
            }}
            onError={setError}
          />
        ) : (
          <WorkCard
            key={item.id}
            item={item}
            busy={busy === item.id}
            confirming={confirming === item.id}
            onEdit={() => setEditing(item.id)}
            onAskDelete={() => setConfirming(item.id)}
            onCancelDelete={() => setConfirming(null)}
            onConfirmDelete={() => void remove(item)}
          />
        ),
      )}
    </div>
  )
}

function WorkCard({
  item,
  busy,
  confirming,
  onEdit,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}: {
  item: WorkItem
  busy: boolean
  confirming: boolean
  onEdit: () => void
  onAskDelete: () => void
  onCancelDelete: () => void
  onConfirmDelete: () => void
}) {
  const percentage = percentageOf(item)
  const unscored = item.status === 'needs_review'

  return (
    <Card className={`!p-4 ${unscored ? 'border-amber-200 bg-amber-50/40' : ''}`}>
      <div className="flex items-center gap-3">
        <span className="text-xl">{subjectIcon(item.subject)}</span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {item.markingId ? (
              <Link
                to={`/marking/${item.markingId}`}
                className="truncate text-sm font-medium text-slate-800 hover:underline"
              >
                {item.title}
              </Link>
            ) : (
              <span className="truncate text-sm font-medium text-slate-800">{item.title}</span>
            )}
            {unscored && <Pill tone="amber">Needs review</Pill>}
          </div>
          <div className="text-xs text-slate-500">
            {item.doneOn ? new Date(item.doneOn).toLocaleDateString() : 'No date'}
            {item.marksAvailable != null && item.marksAwarded != null && (
              <> · {item.marksAwarded}/{item.marksAvailable}</>
            )}
            {item.weakTopics.length > 0 && ` · weak on ${item.weakTopics.slice(0, 2).join(', ')}`}
          </div>
          {unscored && item.reviewReason && (
            <div className="mt-1 text-xs text-amber-800">{item.reviewReason}</div>
          )}
        </div>

        <span className={`text-xl font-bold ${scoreColour(percentage)}`}>
          {percentage != null ? `${Math.round(percentage)}%` : '—'}
        </span>

        {confirming ? (
          <div className="flex shrink-0 items-center gap-2">
            <span className="text-xs text-slate-600">Remove?</span>
            <Button size="sm" variant="danger" disabled={busy} onClick={onConfirmDelete}>
              {busy ? 'Removing…' : 'Yes'}
            </Button>
            <Button size="sm" variant="ghost" onClick={onCancelDelete}>
              No
            </Button>
          </div>
        ) : (
          <div className="flex shrink-0 items-center gap-1">
            <Button
              size="sm"
              variant="secondary"
              onClick={onEdit}
              title={unscored ? 'Mark this by hand' : 'Change the mark or details'}
            >
              {unscored ? 'Mark manually' : 'Edit'}
            </Button>
            <Button size="sm" variant="ghost" onClick={onAskDelete} title="Take off the record">
              Remove
            </Button>
          </div>
        )}
      </div>
    </Card>
  )
}

function EditWorkCard({
  item,
  siblings,
  onCancel,
  onSaved,
  onError,
}: {
  item: WorkItem
  siblings: Child[]
  onCancel: () => void
  onSaved: () => Promise<void>
  onError: (message: string) => void
}) {
  const [title, setTitle] = useState(item.title)
  const [subject, setSubject] = useState(item.subject)
  const [doneOn, setDoneOn] = useState(dayOf(item.doneOn))
  const [awarded, setAwarded] = useState(item.marksAwarded?.toString() ?? '')
  const [available, setAvailable] = useState(item.marksAvailable?.toString() ?? '')
  const [saving, setSaving] = useState(false)

  const preview = useMemo(() => {
    const a = Number(awarded)
    const b = Number(available)
    if (!available || Number.isNaN(a) || Number.isNaN(b) || b <= 0) return null
    return Math.round((a / b) * 1000) / 10
  }, [awarded, available])

  const save = async () => {
    setSaving(true)
    try {
      await api.updateWork(item.id, {
        title,
        subject,
        ...(doneOn ? { doneOn } : {}),
        ...(awarded !== '' ? { marksAwarded: Number(awarded) } : {}),
        ...(available !== '' ? { marksAvailable: Number(available) } : {}),
      })
      await onSaved()
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not save that change')
    } finally {
      setSaving(false)
    }
  }

  const moveTo = async (toChildId: string) => {
    setSaving(true)
    try {
      await api.moveWork(item.id, toChildId)
      await onSaved()
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not move that work')
    } finally {
      setSaving(false)
    }
  }

  const field = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm'

  return (
    <Card className="!p-4">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Title</span>
            <input className={field} value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Subject</span>
            <input className={field} value={subject} onChange={(e) => setSubject(e.target.value)} />
          </label>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Date done</span>
            <input
              type="date"
              className={field}
              value={doneOn}
              onChange={(e) => setDoneOn(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Marks</span>
            <input
              type="number"
              min={0}
              className={field}
              value={awarded}
              onChange={(e) => setAwarded(e.target.value)}
              placeholder="e.g. 41"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">Out of</span>
            <input
              type="number"
              min={1}
              className={field}
              value={available}
              onChange={(e) => setAvailable(e.target.value)}
              placeholder="e.g. 50"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm text-slate-600">
            {preview != null ? `That works out at ${preview}%.` : 'Enter a mark and a total.'}
          </span>
          <div className="flex items-center gap-2">
            {siblings.length > 0 && (
              <select
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                value=""
                disabled={saving}
                onChange={(e) => e.target.value && void moveTo(e.target.value)}
              >
                <option value="">Move to…</option>
                {siblings.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
            <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => void save()} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  )
}
