/**
 * API client for the study programme.
 *
 * A single place that knows how to reach the backend and attach the auth
 * token, so components deal in typed data rather than fetch calls.
 */

import type {
  Assignment,
  Child,
  ChildProgress,
  ChildSubject,
  Marking,
  MarkingListItem,
  Paper,
  RetestResult,
  ScoreLogItem,
  StudyPlan,
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

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function authHeaders(): Promise<Record<string, string>> {
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
    files: File[]
  }) => {
    const form = new FormData()
    form.append('subject', payload.subject)
    form.append('title', payload.title || '')
    form.append('paperType', payload.paperType || 'workbook')
    form.append('weekLabel', payload.weekLabel || '')
    form.append('yearGroup', payload.yearGroup || '')
    form.append('pastedText', payload.pastedText || '')
    payload.files.forEach((file) => form.append('files', file))
    return upload<Paper>('/papers', form)
  },

  deletePaper: (paperId: string) => send<void>('DELETE', `/papers/${paperId}`),

  paperFileUrl: (paperId: string) => `${API_BASE}/papers/${paperId}/file`,

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
