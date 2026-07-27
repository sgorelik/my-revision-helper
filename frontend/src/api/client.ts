/**
 * API client for the study programme.
 *
 * A single place that knows how to reach the backend and attach the auth
 * token, so components deal in typed data rather than fetch calls.
 */

import type {
  Assignment,
  BulkUploadResponse,
  Child,
  ChildProgress,
  ChildSubject,
  Marking,
  MarkingListItem,
  Paper,
  ResourceLink,
  RetestResult,
  ScoreLogItem,
  StudyPlan,
  Today,
  TopicMastery,
  WeekDay,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

/** Supplied by the auth layer so this module does not depend on Auth0. */
type TokenGetter = () => Promise<string | null>

let getToken: TokenGetter = async () => null

export function setTokenGetter(getter: TokenGetter) {
  getToken = getter
}

/**
 * Requests hold until the auth layer reports it knows who the user is.
 *
 * Restoring an Auth0 session is asynchronous, and a request that goes out
 * before it finishes carries no token. The API then answers for the anonymous
 * session rather than the parent, which comes back as empty lists — pages
 * render "nothing here yet" for an account that has plenty. Gating here rather
 * than in each page means a component added later cannot reintroduce the race.
 */
// Bounded: if Auth0 never answers, carrying on unauthenticated shows an empty
// account, whereas waiting forever shows a spinner that never resolves. The
// first is recoverable by reloading, the second is not.
const AUTH_WAIT_MS = 8000

let releaseAuthReady!: () => void
const authReady = Promise.race([
  new Promise<void>((resolve) => {
    releaseAuthReady = resolve
  }),
  new Promise<void>((resolve) => setTimeout(resolve, AUTH_WAIT_MS)),
])

export function markAuthReady() {
  releaseAuthReady()
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  await authReady
  const token = await getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail
    } catch {
      // Response had no JSON body; keep the generic message.
    }
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers: await authHeaders() })
  return handle<T>(response)
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  return handle<T>(response)
}

async function fetchBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}${path}`, { headers: await authHeaders() })
  if (!response.ok) {
    throw new ApiError(`Could not open that file (${response.status})`, response.status)
  }
  return response.blob()
}

/**
 * Open an authenticated file in a new tab.
 *
 * A plain link cannot be used because these endpoints need the bearer token, so
 * the bytes are fetched and handed to the browser as a blob. The tab is opened
 * before the await: popup blockers only allow it during the click itself.
 */
export async function openInNewTab(path: string): Promise<void> {
  const tab = window.open('', '_blank')
  try {
    const url = URL.createObjectURL(await fetchBlob(path))
    if (tab) {
      tab.location.href = url
    } else {
      window.location.href = url
    }
    // Long enough for the tab to load; revoking sooner leaves a blank page.
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (error) {
    tab?.close()
    throw error
  }
}

/** Save an authenticated file to disk under a sensible name. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const url = URL.createObjectURL(await fetchBlob(path))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

async function upload<T>(path: string, form: FormData): Promise<T> {
  // Content-Type is deliberately omitted so the browser sets the multipart boundary.
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: await authHeaders(),
    body: form,
  })
  return handle<T>(response)
}

// --- Children --------------------------------------------------------------

export const api = {
  listChildren: () => get<{ items: Child[] }>('/children').then((r) => r.items),

  createChild: (payload: {
    name: string
    yearGroup?: string
    school?: string
    colour?: string
    avatarEmoji?: string
  }) => send<Child>('POST', '/children', payload),

  updateChild: (childId: string, payload: Partial<Child>) =>
    send<Child>('PATCH', `/children/${childId}`, payload),

  deleteChild: (childId: string) => send<void>('DELETE', `/children/${childId}`),

  getChildSubjects: (childId: string) => get<ChildSubject[]>(`/children/${childId}/subjects`),

  replaceChildSubjects: (childId: string, subjects: Partial<ChildSubject>[]) =>
    send<ChildSubject[]>('PUT', `/children/${childId}/subjects`, subjects),

  getPlan: (childId: string) => get<StudyPlan | null>(`/children/${childId}/plan`),

  // --- Progress ------------------------------------------------------------

  getProgress: (childId: string) => get<ChildProgress>(`/children/${childId}/progress`),

  getToday: (childId: string) => get<Today>(`/children/${childId}/today`),

  getTodo: (childId: string) =>
    get<{ items: Assignment[] }>(`/children/${childId}/todo`).then((r) => r.items),

  getWeek: (childId: string, weekCycle?: 'A' | 'B') =>
    get<WeekDay[]>(`/children/${childId}/week${weekCycle ? `?weekCycle=${weekCycle}` : ''}`),

  getMastery: (childId: string, subject?: string) =>
    get<TopicMastery[]>(
      `/children/${childId}/mastery${subject ? `?subject=${encodeURIComponent(subject)}` : ''}`,
    ),

  getScoreLog: (childId: string) => get<ScoreLogItem[]>(`/children/${childId}/score-log`),

  addScore: (
    childId: string,
    payload: { subject: string; label: string; scorePct: number; yearAveragePct?: number },
  ) => send<ScoreLogItem>('POST', `/children/${childId}/score-log`, payload),

  createRetest: (
    childId: string,
    payload: { markingId?: string; subject?: string; topics?: string[]; questionCount?: number },
  ) => send<RetestResult>('POST', `/children/${childId}/retest`, payload),

  // --- Papers --------------------------------------------------------------

  listPapers: (subject?: string) =>
    get<{ items: Paper[]; total: number }>(
      `/papers${subject ? `?subject=${encodeURIComponent(subject)}` : ''}`,
    ),

  getPaper: (paperId: string, includeText = false) =>
    get<Paper>(`/papers/${paperId}${includeText ? '?includeText=true' : ''}`),

  uploadPaper: (payload: {
    subject: string
    title?: string
    paperType?: string
    weekLabel?: string
    yearGroup?: string
    pastedText?: string
    resourceUrl?: string
    resourceLabel?: string
    files: File[]
  }) => {
    const form = new FormData()
    form.append('subject', payload.subject)
    form.append('title', payload.title || '')
    form.append('paperType', payload.paperType || 'workbook')
    form.append('weekLabel', payload.weekLabel || '')
    form.append('yearGroup', payload.yearGroup || '')
    form.append('pastedText', payload.pastedText || '')
    form.append('resourceUrl', payload.resourceUrl || '')
    form.append('resourceLabel', payload.resourceLabel || '')
    payload.files.forEach((file) => form.append('files', file))
    return upload<Paper>('/papers', form)
  },

  /**
   * Add many documents at once, one paper per file.
   *
   * `meta` carries per-file overrides keyed by filename; anything omitted is
   * inferred server-side from the filename.
   */
  bulkUploadPapers: (payload: {
    files: File[]
    meta?: Record<string, { subject?: string; title?: string; weekLabel?: string; resourceUrl?: string; resourceLabel?: string }>
    subject?: string
    weekLabel?: string
    yearGroup?: string
  }) => {
    const form = new FormData()
    payload.files.forEach((file) => form.append('files', file))
    form.append('meta', JSON.stringify(payload.meta || {}))
    form.append('subject', payload.subject || '')
    form.append('weekLabel', payload.weekLabel || '')
    form.append('yearGroup', payload.yearGroup || '')
    return upload<BulkUploadResponse>('/papers/bulk', form)
  },

  updatePaper: (
    paperId: string,
    payload: {
      title?: string
      subject?: string
      weekLabel?: string
      topics?: string[]
      resources?: ResourceLink[]
    },
  ) => send<Paper>('PATCH', `/papers/${paperId}`, payload),

  deletePaper: (paperId: string) => send<void>('DELETE', `/papers/${paperId}`),

  /**
   * The original upload. Parent-only: for a workbook this still contains the
   * answer key, which is why students are given the generated worksheet instead.
   */
  openPaperFile: (paperId: string) => openInNewTab(`/papers/${paperId}/file`),

  /** The student-safe printable worksheet, built from the parsed questions. */
  openWorksheet: (assignmentId: string) =>
    openInNewTab(`/assignments/${assignmentId}/worksheet`),

  // --- Assignments ---------------------------------------------------------

  listAssignments: (params: { childId?: string; outstanding?: boolean; subject?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.childId) query.set('childId', params.childId)
    if (params.outstanding) query.set('outstanding', 'true')
    if (params.subject) query.set('subject', params.subject)
    const suffix = query.toString() ? `?${query}` : ''
    return get<{ items: Assignment[]; total: number }>(`/assignments${suffix}`)
  },

  getAssignment: (assignmentId: string) => get<Assignment>(`/assignments/${assignmentId}`),

  createAssignment: (payload: {
    childId: string
    title: string
    subject: string
    assignmentType: 'paper' | 'task'
    paperId?: string
    instructions?: string
    resourceUrl?: string
    estimatedMinutes?: number
    dueDate?: string
    scheduledDate?: string
    weekLabel?: string
    verification?: string
  }) => send<Assignment>('POST', '/assignments', payload),

  bulkAssign: (childIds: string[], assignments: Record<string, unknown>[]) =>
    send<{ items: Assignment[]; total: number }>('POST', '/assignments/bulk', {
      childIds,
      assignments,
    }),

  updateAssignment: (assignmentId: string, payload: Record<string, unknown>) =>
    send<Assignment>('PATCH', `/assignments/${assignmentId}`, payload),

  deleteAssignment: (assignmentId: string) => send<void>('DELETE', `/assignments/${assignmentId}`),

  completeTask: (assignmentId: string, payload: { minutesSpent?: number; note?: string }) =>
    send<Assignment>('POST', `/assignments/${assignmentId}/complete`, payload),

  submitWork: (
    assignmentId: string,
    payload: { files: File[]; pastedText?: string; note?: string; minutesSpent?: number },
  ) => {
    const form = new FormData()
    form.append('pastedText', payload.pastedText || '')
    form.append('note', payload.note || '')
    if (payload.minutesSpent != null) form.append('minutesSpent', String(payload.minutesSpent))
    payload.files.forEach((file) => form.append('files', file))
    return upload<Marking>(`/assignments/${assignmentId}/submit`, form)
  },

  // --- Marking -------------------------------------------------------------

  listMarkings: (childId?: string) =>
    get<{ items: MarkingListItem[]; total: number }>(
      `/markings${childId ? `?childId=${childId}` : ''}`,
    ),

  getMarking: (markingId: string) => get<Marking>(`/markings/${markingId}`),

  overrideMark: (
    markingId: string,
    questionMarkId: string,
    payload: { marksAwarded: number; verdict?: string; feedback?: string },
  ) => send<Marking>('PATCH', `/markings/${markingId}/questions/${questionMarkId}`, payload),

  // --- Subjects ------------------------------------------------------------

  getSubjects: () => get<{ subjects: string[] }>('/subjects').then((r) => r.subjects),
}
