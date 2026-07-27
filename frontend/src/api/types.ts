/**
 * Types mirroring the study programme API.
 *
 * Note that no paper or question type carries an expected answer: the answer
 * key never leaves the server for a student-facing view.
 */

export interface Child {
  id: string
  name: string
  yearGroup?: string | null
  school?: string | null
  colour: string
  avatarEmoji?: string | null
  isActive: boolean
  createdAt: string
}

export interface ChildSubject {
  id: string
  subject: string
  baselineScore?: number | null
  yearAverage?: number | null
  targetScore?: number | null
  weeklyMinutes: number
  priority: number
  focusTopics: string[]
  reportNotes?: string | null
  gap?: number | null
}

export interface PlanBlock {
  id: string
  dayOfWeek: number
  blockIndex: number
  subject: string
  focus?: string | null
  plannedMinutes: number
  weekCycle?: string | null
}

export interface StudyPlan {
  id: string
  childId: string
  title: string
  summary?: string | null
  startDate?: string | null
  endDate?: string | null
  weeklyMinutesTarget: number
  daysPerWeek: number
  isActive: boolean
  blocks: PlanBlock[]
}

/** The outcome for one file in a bulk upload, so failures can be retried alone. */
export interface BulkUploadItem {
  filename: string
  status: 'ok' | 'failed'
  paper?: Paper | null
  error?: string | null
}

export interface BulkUploadResponse {
  items: BulkUploadItem[]
  succeeded: number
  failed: number
}

/** A "watch this first" link. Belongs to the material, so it travels with it. */
export interface ResourceLink {
  url: string
  label?: string | null
  kind: string
}

export interface PaperQuestion {
  id: string
  number: string
  orderIndex: number
  questionText: string
  sessionLabel?: string | null
  band?: string | null
  topic?: string | null
  marks: number
}

export interface Paper {
  id: string
  title: string
  subject: string
  paperType: string
  topics: string[]
  weekLabel?: string | null
  questionCount: number
  totalMarks?: number | null
  estimatedMinutes?: number | null
  hasAnswerKey: boolean
  /** False when the upload contains an answer key, so it must not go to a student. */
  originalIsStudentSafe: boolean
  resources: ResourceLink[]
  parseStatus: string
  createdAt: string
  questions?: PaperQuestion[]
  questionText?: string | null
  sourceFileId?: string | null
  parseError?: string | null
}

export interface MarkingSummary {
  id: string
  percentage?: number | null
  marksAwarded?: number | null
  marksAvailable?: number | null
  weakTopics: string[]
  markedAt?: string | null
}

export type AssignmentStatus = 'todo' | 'in_progress' | 'submitted' | 'marked' | 'done'

export interface Assignment {
  id: string
  childId: string
  title: string
  subject: string
  assignmentType: 'paper' | 'task'
  paperId?: string | null
  instructions?: string | null
  resourceUrl?: string | null
  /** The paper's links plus this assignment's extras, already merged server-side. */
  resources: ResourceLink[]
  estimatedMinutes?: number | null
  dueDate?: string | null
  weekLabel?: string | null
  verification: 'upload' | 'self_report' | 'timer' | 'none'
  status: AssignmentStatus
  sortOrder: number
  createdAt: string
  completedAt?: string | null
  questionCount: number
  latestMarking?: MarkingSummary | null
}

export interface QuestionMark {
  id: string
  orderIndex: number
  questionNumber?: string | null
  questionText?: string | null
  studentAnswer?: string | null
  expectedAnswer?: string | null
  marksAwarded: number
  marksAvailable: number
  verdict?: 'correct' | 'partial' | 'incorrect' | 'not_attempted' | null
  feedback?: string | null
  topic?: string | null
}

export interface Marking {
  id: string
  submissionId: string
  childId: string
  assignmentId?: string | null
  paperId?: string | null
  subject: string
  marksAwarded?: number | null
  marksAvailable?: number | null
  percentage?: number | null
  overallFeedback?: string | null
  strengths: string[]
  weaknesses: string[]
  weakTopics: string[]
  markedBy: string
  markedAt?: string | null
  questionMarks: QuestionMark[]
}

export interface MarkingListItem {
  id: string
  assignmentId?: string | null
  assignmentTitle?: string | null
  subject: string
  percentage?: number | null
  marksAwarded?: number | null
  marksAvailable?: number | null
  weakTopics: string[]
  markedAt?: string | null
}

export interface TopicMastery {
  subject: string
  topic: string
  attempts: number
  masteryPct?: number | null
  status: 'weak' | 'developing' | 'secure'
  lastAssessedAt?: string | null
}

export interface SubjectProgress {
  subject: string
  baselineScore?: number | null
  yearAverage?: number | null
  targetScore?: number | null
  latestScore?: number | null
  gapToAverage?: number | null
  baselineGap?: number | null
  weeklyMinutes: number
  assignmentsTotal: number
  assignmentsDone: number
  minutesLogged: number
  weakTopics: string[]
}

export interface ScoreLogItem {
  id: string
  subject: string
  label: string
  scorePct?: number | null
  yearAveragePct?: number | null
  gap?: number | null
  source: string
  recordedAt: string
}

export interface ChildProgress {
  child: Child
  plan?: StudyPlan | null
  subjects: SubjectProgress[]
  scoreLog: ScoreLogItem[]
  weakTopics: TopicMastery[]
  upNext: Assignment[]
  recentMarkings: MarkingListItem[]
  assignmentsTotal: number
  assignmentsDone: number
  assignmentsDueThisWeek: number
  assignmentsOverdue: number
  minutesLoggedThisWeek: number
  weeklyMinutesTarget: number
  averagePercentage?: number | null
  streakDays: number
}

export interface RetestResult {
  revisionId: string
  runId?: string | null
  subject: string
  topics: string[]
  questionCount: number
}

export interface WeekDayBlock {
  blockIndex: number
  subject: string
  focus?: string | null
  plannedMinutes: number
  weekCycle?: string | null
  assignments: Assignment[]
}

export interface WeekDay {
  dayOfWeek: number
  date: string
  blocks: WeekDayBlock[]
  unscheduled: Assignment[]
}
