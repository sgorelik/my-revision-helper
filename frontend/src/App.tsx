import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  Card,
  CardBody,
  CardHeader,
  Button,
  Input,
  Textarea,
  Chip,
  Table,
  TableHeader,
  TableColumn,
  TableBody,
  TableRow,
  TableCell,
  Select,
  SelectItem,
  Pagination,
} from '@heroui/react'
import {
  PhotoIcon,
  CheckCircleIcon,
  XCircleIcon,
  XMarkIcon,
  DocumentIcon,
  PresentationChartBarIcon,
  TrashIcon,
  ArrowRightIcon,
  PlusIcon,
  ExclamationTriangleIcon,
  FlagIcon,
} from '@heroicons/react/24/outline'
import Logo from './Logo'
import { useAuth } from './auth'

type RevisionConfig = {
  id?: string
  name: string
  subject: string
  topics: string[]
  description?: string
  desiredQuestionCount: number
  accuracyThreshold: number
  questionStyle?: 'free-text' | 'multiple-choice'
  uploadedFiles?: string[] | null
  extractedTextPreview?: string | null
}

type Question = {
  id: string
  text: string
  questionStyle?: 'free-text' | 'multiple-choice'
  options?: string[]  // For multiple choice questions
  correctAnswerIndex?: number  // For multiple choice questions (0-based index)
  rationale?: string  // Prefetched explanation for multiple choice questions
}

type AnswerResult = {
  questionId: string
  questionText?: string | null
  studentAnswer: string
  isCorrect: boolean  // Kept for backward compatibility
  score: string  // "Full Marks", "Partial Marks", or "Incorrect"
  correctAnswer: string
  explanation?: string | null
  error?: string | null
}

type RevisionSummary = {
  revisionId: string
  questions: AnswerResult[]
  overallAccuracy: number
}

type CompletedRun = {
  runId: string
  revisionId: string
  revisionName: string
  subject: string
  completedAt: string
  score: number
  totalQuestions: number
  threshold: number
}

type RevisionRun = {
  id: string
  revisionId: string
  status: string
}

// API base URL - uses environment variable if set, otherwise defaults to relative path
// Vite proxy forwards /api to http://localhost:8000 in development
// In production, backend serves frontend from same domain, so relative path works
const API_BASE = import.meta.env.VITE_API_BASE || '/api'

async function createRevision(
  config: RevisionConfig,
  files?: File[],
  token?: string | null
): Promise<RevisionConfig> {
  const formData = new FormData()
  formData.append('name', config.name)
  formData.append('subject', config.subject)
  formData.append('description', config.description ?? '')
  formData.append('desiredQuestionCount', String(config.desiredQuestionCount))
  formData.append('accuracyThreshold', String(config.accuracyThreshold))
  formData.append('topics', JSON.stringify(config.topics))
  formData.append('questionStyle', config.questionStyle || 'free-text')
  
  // Add files if provided
  if (files && files.length > 0) {
    files.forEach((file) => {
      formData.append('files', file)
    })
  }

  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}/revisions`, {
    method: 'POST',
    headers,
    body: formData,
  })
  if (!res.ok) {
    const errorText = await res.text()
    let errorMessage = 'Failed to create revision'
    try {
      const errorJson = JSON.parse(errorText)
      errorMessage = errorJson.detail || errorMessage
    } catch {
      errorMessage = errorText || errorMessage
    }
    throw new Error(errorMessage)
  }
  return res.json()
}

async function listRevisions(token?: string | null): Promise<RevisionConfig[]> {
  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/revisions`, { headers })
  if (!res.ok) {
    // 404 is OK - means no revisions exist yet
    if (res.status === 404) {
      return []
    }
    throw new Error('Failed to load revisions')
  }
  return res.json()
}

async function getSubjects(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/subjects`)
  if (!res.ok) {
    throw new Error('Failed to load subjects')
  }
  const data = await res.json()
  return data.subjects || []
}

async function startRun(revisionId: string, token?: string | null): Promise<RevisionRun> {
  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/revisions/${revisionId}/runs`, {
    method: 'POST',
    headers,
  })
  if (!res.ok) throw new Error('Failed to start run')
  return res.json()
}

async function getNextQuestion(runId: string, token?: string | null): Promise<Question | null> {
  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/runs/${runId}/next-question`, { headers })
  if (!res.ok) throw new Error('Failed to load question')
  const data = await res.json()
  if (!data) return null
  
  // Return full question data including multiple choice fields
  const question: Question = {
    id: data.id,
    text: data.text,
  }
  if (data.questionStyle) {
    question.questionStyle = data.questionStyle
  }
  if (data.options) {
    question.options = data.options
  }
  if (data.correctAnswerIndex !== undefined && data.correctAnswerIndex !== null) {
    question.correctAnswerIndex = data.correctAnswerIndex
  }
  if (data.rationale) {
    question.rationale = data.rationale
  }
  return question
}

async function getQuestionCount(runId: string, token?: string | null): Promise<number> {
  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/runs/${runId}/question-count`, { headers })
  if (!res.ok) return 0
  const data = await res.json()
  return data.totalQuestions || 0
}

async function submitAnswer(
  runId: string,
  questionId: string,
  answer: string,
  token?: string | null
): Promise<AnswerResult> {
  const headers: HeadersInit = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/runs/${runId}/answers`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ questionId, answer }),
  })
  if (!res.ok) throw new Error('Failed to submit answer')
  return res.json()
}

async function getRunSummary(runId: string, token?: string | null): Promise<RevisionSummary> {
  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/runs/${runId}/summary`, { headers })
  if (!res.ok) throw new Error('Failed to load summary')
  return res.json()
}

async function listCompletedRuns(token?: string | null): Promise<CompletedRun[]> {
  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/runs/completed`, { headers })
  if (!res.ok) {
    if (res.status === 404) {
      return []
    }
    throw new Error('Failed to load completed runs')
  }
  return res.json()
}

async function checkPrep(
  subject: string,
  description: string,
  files: File[],
  previousPrepCheckId?: string | null,
  token?: string | null
): Promise<{ feedback: string; prepCheckId?: string }> {
  const formData = new FormData()
  formData.append('subject', subject)
  formData.append('description', description || '')
  if (previousPrepCheckId) {
    formData.append('previousPrepCheckId', previousPrepCheckId)
  }
  
  // Add files if provided
  if (files && files.length > 0) {
    files.forEach((file) => {
      formData.append('files', file)
    })
  }

  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}/prep-check`, {
    method: 'POST',
    headers,
    body: formData,
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to check prep work' }))
    throw new Error(error.detail || 'Failed to check prep work')
  }
  return res.json()
}

async function flagQuestion(runId: string, questionId: string, flagType: string, token?: string | null): Promise<void> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/runs/${runId}/questions/${questionId}/flag`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ flagType }),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to flag question' }))
    throw new Error(error.detail || 'Failed to flag question')
  }
}

async function deleteRevision(revisionId: string, token?: string | null): Promise<void> {
  const headers: HeadersInit = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}/revisions/${revisionId}`, {
    method: 'DELETE',
    headers,
  })
  if (!res.ok) {
    const errorText = await res.text()
    let errorMessage = 'Failed to delete revision'
    try {
      const errorJson = JSON.parse(errorText)
      errorMessage = errorJson.detail || errorMessage
    } catch {
      errorMessage = errorText || errorMessage
    }
    throw new Error(errorMessage)
  }
}

function App() {
  // Auth hook - works with or without Auth0 configured
  const { user, isAuthenticated, isLoading: authLoading, login, logout, getToken } = useAuth()
  
  // Debug: Log Auth0 env var status
  useEffect(() => {
    const hasAuth0Domain = !!import.meta.env.VITE_AUTH0_DOMAIN
    console.log('Auth0 Domain configured:', hasAuth0Domain, hasAuth0Domain ? import.meta.env.VITE_AUTH0_DOMAIN : 'NOT SET')
    if (!hasAuth0Domain) {
      console.warn('⚠️ VITE_AUTH0_DOMAIN is not set - login button will not appear')
    }
  }, [])
  
  const [revision, setRevision] = useState<RevisionConfig | null>(null)
  const [run, setRun] = useState<RevisionRun | null>(null)
  const [knownRevisions, setKnownRevisions] = useState<RevisionConfig[]>([])
  const [completedRuns, setCompletedRuns] = useState<CompletedRun[]>([])
  const [showRevisionList, setShowRevisionList] = useState(false)
  const [currentPage, setCurrentPage] = useState<'home' | 'create' | 'prep-check'>('home')
  const [prepCheckState, setPrepCheckState] = useState<'config' | 'checking' | 'results' | null>(null)
  const [prepCheckForm, setPrepCheckForm] = useState({
    subject: '',
    description: '',
    previousPrepCheckId: null as string | null,
  })
  const [prepCheckFiles, setPrepCheckFiles] = useState<File[]>([])
  const [prepCheckResult, setPrepCheckResult] = useState<string | null>(null)
  const [prepCheckId, setPrepCheckId] = useState<string | null>(null)
  const [isCheckingPrep, setIsCheckingPrep] = useState(false)
  const [previousPrepChecks, setPreviousPrepChecks] = useState<Array<{id: string; subject: string; createdAt: string}>>([])
  const [form, setForm] = useState({
    name: '',
    subject: '',
    description: '',
    desiredQuestionCount: 10,
    accuracyThreshold: 80,
    questionStyle: 'free-text' as 'free-text' | 'multiple-choice',
  })
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [isProcessingFiles, setIsProcessingFiles] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Shared styling for all Input and Textarea components - Calculator color scheme
  const inputClassNames = {
    label: "mb-2 text-orange-600",
    input: "px-3 py-2 text-gray-700",
    inputWrapper: "rounded-lg border-2 border-orange-200 hover:border-orange-400",
    placeholder: "px-3 text-gray-400"
  }

  // Styling for Select dropdown to match Input components - Calculator color scheme
  const selectClassNames = {
    label: "mb-2 text-orange-600",
    trigger: "rounded-lg border-2 border-orange-200 hover:border-orange-400 px-3 min-h-unit-12",
    value: "px-3 text-gray-700",
    popoverContent: "rounded-lg border-2 border-orange-200 bg-white shadow-md p-3 max-w-full",
    listbox: "bg-white flex flex-wrap gap-2 max-w-full",
    listboxItem: "bg-white text-gray-900 min-h-0 h-auto",
  }

  // Shared styling for buttons with icons - prevents icon and text from wrapping
  // base: "inline-flex w-auto" lets the button size to its content instead of squeezing
  // content: "gap-1 whitespace-nowrap" keeps the icon and text together on one line
  const buttonWithIconClassName = "inline-flex w-auto [&>span]:gap-1 [&>span]:whitespace-nowrap"

  // Subjects list (loaded from backend)
  const [subjects, setSubjects] = useState<string[]>([])
  const [question, setQuestion] = useState<Question | null>(null)
  const [answer, setAnswer] = useState('')
  const [lastResult, setLastResult] = useState<AnswerResult | null>(null)
  const [isSubmittingAnswer, setIsSubmittingAnswer] = useState(false)
  const [summary, setSummary] = useState<RevisionSummary | null>(null)
  const [totalQuestions, setTotalQuestions] = useState<number>(0)
  const [currentQuestionNumber, setCurrentQuestionNumber] = useState<number>(0)
  const [lastAnsweredQuestionId, setLastAnsweredQuestionId] = useState<string | null>(null)
  const [isLoadingQuestion, setIsLoadingQuestion] = useState(false)
  const [isStartingRun, setIsStartingRun] = useState(false)
  const [userImageError, setUserImageError] = useState(false)
  const [formErrors, setFormErrors] = useState<{name?: string; subject?: string; description?: string}>({})
  const [answerError, setAnswerError] = useState<string | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<{isOpen: boolean; revisionId: string | null}>({isOpen: false, revisionId: null})
  const [revisionsPage, setRevisionsPage] = useState(1)
  const [completedRunsPage, setCompletedRunsPage] = useState(1)
  const itemsPerPage = 5
  const [flagModal, setFlagModal] = useState<{isOpen: boolean; questionId: string | null}>({isOpen: false, questionId: null})
  const [isSubmittingFlag, setIsSubmittingFlag] = useState(false)


  const loadRevisions = async () => {
    try {
      const token = await getToken()
      const revs = await listRevisions(token)
      setKnownRevisions(revs)
    } catch (err: any) {
      setError(err.message ?? 'Failed to load revisions')
    }
  }

  const loadCompletedRuns = async () => {
    // Only load completed runs for authenticated users
    if (!isAuthenticated) {
      setCompletedRuns([])
      return
    }
    try {
      const token = await getToken()
      const runs = await listCompletedRuns(token)
      setCompletedRuns(runs)
    } catch (err: any) {
      setError(err.message ?? 'Failed to load completed runs')
    }
  }

  const handleDeleteRevision = (revisionId: string) => {
    if (!isAuthenticated) {
      setError('You must be logged in to delete revisions')
      return
    }
    if (!revisionId) {
      console.error('Cannot delete revision: revisionId is missing')
      return
    }
    // Open confirmation modal
    setDeleteConfirm({isOpen: true, revisionId})
  }

  const confirmDeleteRevision = async () => {
    if (!deleteConfirm.revisionId) return
    try {
      setError(null)
      const token = await getToken()
      await deleteRevision(deleteConfirm.revisionId, token)
      // Reload revisions after deletion
      await loadRevisions()
      await loadCompletedRuns()
      setDeleteConfirm({isOpen: false, revisionId: null})
    } catch (err: any) {
      setError(err.message ?? 'Failed to delete revision')
      setDeleteConfirm({isOpen: false, revisionId: null})
    }
  }

  const loadSubjects = async () => {
    try {
      const subjList = await getSubjects()
      setSubjects(subjList)
    } catch (err: any) {
      // Fallback to default subjects if API fails
      setSubjects([
        "Mathematics",
        "Science",
        "English",
        "History",
        "Geography",
        "Art",
        "Music",
        "Physical Education",
        "Computer Science",
        "Foreign Languages",
        "Other"
      ])
    }
  }

  const onChangeForm = (field: keyof typeof form, value: string | number | 'free-text' | 'multiple-choice') => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleCreateRevision = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setFormErrors({})
    
    // Validate form
    const errors: {name?: string; subject?: string; description?: string} = {}
    if (!form.name.trim()) {
      errors.name = 'Revision name cannot be left blank'
    }
    if (!form.subject) {
      errors.subject = 'Please select a subject'
    }
    if (!form.description.trim() && selectedFiles.length === 0) {
      errors.description = 'Please provide a description or upload files'
    }
    
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors)
      return
    }
    
    setIsCreating(true)
    setIsProcessingFiles(selectedFiles.length > 0)
    try {
      const token = await getToken()
      const created = await createRevision(
        {
          name: form.name,
          subject: form.subject,
          topics: [], // Topics removed - not currently used
          description: form.description,
          desiredQuestionCount: form.desiredQuestionCount,
          accuracyThreshold: form.accuracyThreshold,
          questionStyle: form.questionStyle,
        },
        selectedFiles.length > 0 ? selectedFiles : undefined,
        token
      )
      setRevision(created)

      // Start a run for this revision and load the first question
      if (created.id) {
        setIsStartingRun(true)
        try {
          const newRun = await startRun(created.id, token)
          setRun(newRun)
          setShowRevisionList(false)

          // Get total question count and set initial question number
          const total = await getQuestionCount(newRun.id, token)
          setTotalQuestions(total)
          setCurrentQuestionNumber(1)
          setLastAnsweredQuestionId(null)

          const q = await getNextQuestion(newRun.id, token)
          setQuestion(q)
          setAnswer('')
          setLastResult(null)
          setSummary(null)
          await loadRevisions()
          await loadCompletedRuns()
          // Navigate away from create page (will show run page automatically)
          setCurrentPage('home')
        } finally {
          setIsStartingRun(false)
        }
      }
      // Clear selected files after successful creation
      setSelectedFiles([])
    } catch (err: any) {
      setError(err.message ?? 'Failed to create revision')
    } finally {
      setIsCreating(false)
      setIsProcessingFiles(false)
    }
  }

  // Load subjects on component mount
  useEffect(() => {
    loadSubjects()
  }, [])

  const handleSubmitAnswer = async () => {
    if (!run || !question) return
    
    // Validate answer
    if (!answer.trim()) {
      setAnswerError('Answer cannot be left blank')
      return
    }
    
    // For multiple choice, ensure we have a valid selection
    if (question.questionStyle === 'multiple-choice' && question.options) {
      const validAnswers = [
        ...question.options.map((_, i) => String.fromCharCode(65 + i)), // A, B, C, D
        ...question.options.map((_, i) => String(i)), // 0, 1, 2, 3
        ...question.options, // Option text itself
      ]
      if (!validAnswers.includes(answer.trim())) {
        setAnswerError('Please select an answer option')
        return
      }
    }
    
    setAnswerError(null)
    setIsSubmittingAnswer(true)
    setError(null)
    try {
      const token = await getToken()
      const res = await submitAnswer(run.id, question.id, answer, token)
      setLastResult(res)
      
      // Track that this question has been answered (prevents double-counting on resubmission)
      if (lastAnsweredQuestionId !== question.id) {
        setLastAnsweredQuestionId(question.id)
      }
    } catch (err: any) {
      const errorMessage = err.message ?? 'Failed to submit answer'
      // Check for model-specific errors
      if (errorMessage.includes('model') || errorMessage.includes('OpenAI') || errorMessage.includes('API')) {
        setError(`AI evaluation unavailable: ${errorMessage}. Please try again or contact support.`)
      } else {
        setError(errorMessage)
      }
    } finally {
      setIsSubmittingAnswer(false)
    }
  }

  const handleNextQuestion = async () => {
    if (!run) return
    setIsLoadingQuestion(true)
    try {
      const token = await getToken()
      const q = await getNextQuestion(run.id, token)
      setQuestion(q)
      setAnswer('')
      setLastResult(null)
      setLastAnsweredQuestionId(null) // Reset when moving to new question
      if (q) {
        setCurrentQuestionNumber(prev => prev + 1)
      }
    } catch (err: any) {
      setError(err.message ?? 'Failed to load next question')
    } finally {
      setIsLoadingQuestion(false)
    }
  }

  const handleFinishEarly = async () => {
    if (!run) return
    try {
      // Allow viewing summary for current session run, even without authentication
      // Authentication is only required for viewing summaries from other sessions
      const token = await getToken()
      const s = await getRunSummary(run.id, token)
      setSummary(s)
      setQuestion(null)
      setAnswer('')
      setLastResult(null)
      // Reload completed runs after finishing (only if authenticated)
      if (isAuthenticated) {
        await loadCompletedRuns()
      }
    } catch (err: any) {
      setError(err.message ?? 'Failed to load summary')
    }
  }

  const handleLaunchRevision = async (revisionId: string) => {
    setError(null)
    setIsStartingRun(true)
    // Set revision immediately so the loading screen shows
    const rev = knownRevisions.find(r => r.id === revisionId)
    if (rev) {
      setRevision(rev)
      setShowRevisionList(false)
    }
    try {
      const token = await getToken()
      const newRun = await startRun(revisionId, token)
      if (rev) {
        setRun(newRun)
        // Load question count and first question
        const count = await getQuestionCount(newRun.id, token)
        setTotalQuestions(count)
        setCurrentQuestionNumber(1)
        setLastAnsweredQuestionId(null)
        const q = await getNextQuestion(newRun.id, token)
        setQuestion(q)
      }
    } catch (err: any) {
      setError(err.message ?? 'Failed to start revision')
    } finally {
      setIsStartingRun(false)
    }
  }

  const handleViewSummary = async (runId: string) => {
    if (!isAuthenticated) {
      setError('You must be logged in to view revision summaries')
      return
    }
    try {
      setError(null)
      const token = await getToken()
      const s = await getRunSummary(runId, token)
      setSummary(s)
      setRevision(null)
      setRun(null)
      setQuestion(null)
      setShowRevisionList(false)
    } catch (err: any) {
      setError(err.message ?? 'Failed to load summary')
    }
  }

  const handleBackToHome = () => {
    setRevision(null)
    setRun(null)
    setQuestion(null)
    setSummary(null)
    setAnswer('')
    setLastResult(null)
    setCurrentQuestionNumber(0)
    setLastAnsweredQuestionId(null)
    setTotalQuestions(0)
    setShowRevisionList(true)
    setCurrentPage('home')
    setPrepCheckState(null)
    setPrepCheckResult(null)
    setPrepCheckId(null)
    setPrepCheckForm({ subject: '', description: '', previousPrepCheckId: null })
    setPrepCheckFiles([])
    setPreviousPrepChecks([])
  }

  const handleStartPrepCheck = () => {
    setCurrentPage('prep-check')
    setPrepCheckState('config')
    setShowRevisionList(false)
    loadPreviousPrepChecks()
  }

  const handleSubmitPrepCheck = async () => {
    if (!prepCheckForm.subject || (prepCheckFiles.length === 0 && !prepCheckForm.description)) {
      setError('Please provide a subject and either upload files or provide a description')
      return
    }
    
    setIsCheckingPrep(true)
    setPrepCheckState('checking')
    setError(null)
    
    try {
      const token = await getToken()
      const result = await checkPrep(
        prepCheckForm.subject,
        prepCheckForm.description,
        prepCheckFiles,
        prepCheckForm.previousPrepCheckId,
        token
      )
      setPrepCheckResult(result.feedback)
      setPrepCheckId(result.prepCheckId || null)
      setPrepCheckState('results')
    } catch (err: any) {
      setError(err.message ?? 'Failed to check prep work')
      setPrepCheckState('config')
    } finally {
      setIsCheckingPrep(false)
    }
  }

  const loadPreviousPrepChecks = async () => {
    try {
      const token = await getToken()
      const headers: HeadersInit = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }
      const res = await fetch(`${API_BASE}/prep-checks`, { headers })
      if (res.ok) {
        const checks = await res.json()
        setPreviousPrepChecks(checks.map((c: any) => ({
          id: c.id,
          subject: c.subject,
          createdAt: c.createdAt,
        })))
      }
    } catch (err) {
      // Silently fail - previous prep checks are optional
      console.warn('Failed to load previous prep checks:', err)
    }
  }

  const handleLoadSummary = async () => {
    if (!run) return
    try {
      const token = await getToken()
      const s = await getRunSummary(run.id, token)
      setSummary(s)
    } catch (err: any) {
      setError(err.message ?? 'Failed to load summary')
    }
  }

  // Auto-load summary when no more questions
  useEffect(() => {
    if (run && !question && !summary && totalQuestions > 0) {
      // Small delay to show animation
      const timer = setTimeout(() => {
        handleLoadSummary()
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [run, question, summary, totalQuestions])

  // Load revisions and completed runs on mount and when auth state changes
  useEffect(() => {
    if (!authLoading) {
      loadRevisions()
      loadCompletedRuns()
      setShowRevisionList(true)
    }
  }, [authLoading, isAuthenticated])

  // Reset pagination when lists change
  useEffect(() => {
    const maxPage = Math.ceil(knownRevisions.length / itemsPerPage)
    if (revisionsPage > maxPage && maxPage > 0) {
      setRevisionsPage(maxPage)
    } else if (knownRevisions.length === 0) {
      setRevisionsPage(1)
    }
  }, [knownRevisions.length, revisionsPage])

  useEffect(() => {
    const maxPage = Math.ceil(completedRuns.length / itemsPerPage)
    if (completedRunsPage > maxPage && maxPage > 0) {
      setCompletedRunsPage(maxPage)
    } else if (completedRuns.length === 0) {
      setCompletedRunsPage(1)
    }
  }, [completedRuns.length, completedRunsPage])

  // Reset image error when user changes
  useEffect(() => {
    if (user) {
      setUserImageError(false)
    }
  }, [user?.sub, user?.picture])

  // Show loading state while Auth0 initializes (only if Auth0 is configured)
  if (authLoading && import.meta.env.VITE_AUTH0_DOMAIN) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-yellow-50 to-orange-50 flex items-center justify-center">
        <div className="text-center">
          <Logo size="xl" />
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-yellow-50 to-orange-50">
      {/* Consistent Header Bar */}
      <header className="sticky top-0 z-50 bg-white border-b-2 border-orange-200 shadow-sm">
        <div className="max-w-6xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            {/* Logo (left) - acts as Home */}
            <button
              onClick={handleBackToHome}
              className="flex items-center gap-3 hover:opacity-80 transition-opacity cursor-pointer"
              aria-label="Home"
            >
              <Logo size="md" />
              <span className="text-xl font-semibold text-orange-900 hidden sm:inline">MY PREP PAL</span>
            </button>

            {/* Right side - Auth actions */}
            <div className="flex items-center gap-3">
              {isAuthenticated && user ? (
                <>
                  {/* User info - show on larger screens */}
                  <div className="hidden md:flex items-center gap-2 text-sm text-gray-700">
                    {user.picture && !userImageError ? (
                      <img 
                        src={user.picture} 
                        alt={user.name || user.email || 'User'} 
                        className="w-8 h-8 rounded-full border-2 border-orange-300"
                        onError={() => setUserImageError(true)}
                      />
                    ) : (
                      <div className="w-8 h-8 rounded-full border-2 border-orange-300 bg-gradient-to-r from-orange-400 to-cyan-400 flex items-center justify-center">
                        <span className="text-white font-bold text-sm">
                          {(user.name || user.email || 'U').charAt(0).toUpperCase()}
                        </span>
                      </div>
                    )}
                    <span className="font-medium">{user.name || user.email}</span>
                  </div>
                  {/* Sign Out button - primary action */}
                  <Button
                    onClick={logout}
                    size="sm"
                    className="bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all"
                  >
                    Sign Out
                  </Button>
                </>
              ) : (
                import.meta.env.VITE_AUTH0_DOMAIN && (
                  <Button
                    onClick={login}
                    size="sm"
                    className="bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all"
                  >
                    Sign In
                  </Button>
                )
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Session-only mode banner (only for unauthenticated users) */}
      {!isAuthenticated && import.meta.env.VITE_AUTH0_DOMAIN && (
        <div className="bg-yellow-50 border-b border-yellow-200">
          <div className="max-w-6xl mx-auto px-4 py-2">
            <div className="flex items-center gap-2 text-sm text-yellow-800">
              <svg className="h-4 w-4 text-yellow-600 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <span><strong>Session-only mode:</strong> Your work won't be saved. <button onClick={login} className="font-semibold underline hover:text-yellow-900 cursor-pointer">Sign in</button> to save your progress.</span>
            </div>
          </div>
        </div>
      )}

      <div className="max-w-6xl mx-auto px-4 py-6">

      {/* Revision Lists View (Homepage) */}
      {currentPage === 'home' && showRevisionList && !revision && !summary && (
        <div className="space-y-6">
          {/* Check my Prep Card */}
          <Card className="border border-gray-200 shadow-sm bg-gradient-to-r from-cyan-50 to-orange-50">
            <CardBody className="p-6">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <CheckCircleIcon className="w-6 h-6 text-cyan-600" />
                    <h2 className="text-2xl font-semibold text-gray-900">Check my Prep</h2>
                  </div>
                  <p className="text-gray-700 mb-4">
                    Friendly AI companion that will check the quality of your prep work, BUT WILL NOT do your prep for you.
                  </p>
                  <Button
                    onClick={handleStartPrepCheck}
                    className="bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all"
                    startContent={<CheckCircleIcon className="w-4 h-4" />}
                  >
                    Check my Prep
                  </Button>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* Revisions Section - Unified */}
          <Card className="border border-gray-200 shadow-sm">
            <CardHeader className="border-b border-gray-200 bg-white">
              <div className="flex items-center justify-between w-full">
                <h2 className="text-2xl font-semibold text-gray-900">Revisions</h2>
                <Button
                  onClick={() => setCurrentPage('create')}
                  size="sm"
                  className={`bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all ${buttonWithIconClassName}`}
                  startContent={<PlusIcon className="w-4 h-4" />}
                >
                  Create New
                </Button>
              </div>
            </CardHeader>
            <CardBody className="p-4">
              {knownRevisions.length > 0 ? (
                <>
                  <div className="space-y-2">
                    {[...knownRevisions]
                      .reverse()
                      .slice((revisionsPage - 1) * itemsPerPage, revisionsPage * itemsPerPage)
                      .map((r) => (
                    <div key={r.id} className="border border-gray-200 rounded-lg p-4 bg-white">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="font-semibold text-base text-gray-900">{r.name}</h3>
                          <Chip size="sm" variant="flat" className="mt-1">
                            {r.subject}
                          </Chip>
                          {r.uploadedFiles && r.uploadedFiles.length > 0 && (
                            <div className="flex items-center gap-1 mt-2 text-sm text-gray-600">
                              <PhotoIcon className="w-3 h-3" />
                              <span>Files: {r.uploadedFiles.join(', ')}</span>
                            </div>
                          )}
                          {r.extractedTextPreview && (
                            <p className="text-sm text-gray-500 italic mt-2 line-clamp-2">
                              "{r.extractedTextPreview}"
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                          <Button
                            onClick={() => r.id && handleLaunchRevision(r.id)}
                            size="sm"
                            className="bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all whitespace-nowrap"
                            isDisabled={!r.id}
                          >
                            Start
                          </Button>
                          {isAuthenticated && r.id && (
                          <Button
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              if (r.id) {
                                handleDeleteRevision(r.id)
                              }
                            }}
                            size="sm"
                            variant="flat"
                            className={`border border-red-300 text-red-700 bg-white hover:bg-red-50 rounded-lg font-semibold transition-all ${buttonWithIconClassName}`}
                            startContent={<TrashIcon className="w-4 h-4" />}
                          >
                            Delete
                          </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                  </div>
                  {knownRevisions.length > itemsPerPage && (
                    <div className="flex justify-center mt-4">
                      <Pagination
                        total={Math.ceil(knownRevisions.length / itemsPerPage)}
                        page={revisionsPage}
                        onChange={setRevisionsPage}
                        color="warning"
                        classNames={{
                          wrapper: "gap-0",
                          base: "gap-0",
                          item: "w-8 h-8 text-sm rounded-lg border-2 border-orange-200 bg-white hover:bg-orange-50 data-[selected=true]:bg-gradient-to-r data-[selected=true]:from-orange-600 data-[selected=true]:to-cyan-600 data-[selected=true]:text-white data-[selected=true]:border-orange-400",
                          cursor: "hidden",
                          prev: "rounded-lg border-2 border-orange-200 bg-white hover:bg-orange-50",
                          next: "rounded-lg border-2 border-orange-200 bg-white hover:bg-orange-50",
                        }}
                      />
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <p className="mb-4">No revisions yet.</p>
                  <Button
                    onClick={() => setCurrentPage('create')}
                    size="sm"
                    className={`bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all ${buttonWithIconClassName}`}
                    startContent={<PlusIcon className="w-4 h-4" />}
                  >
                    Create Your First Revision
                  </Button>
                </div>
              )}
            </CardBody>
          </Card>

          {/* Completed Revisions - Only show for authenticated users */}
          {isAuthenticated && completedRuns.length > 0 && (
            <Card className="border border-gray-200 shadow-sm">
              <CardHeader className="border-b border-gray-200 bg-white">
                <div className="flex items-center gap-2">
                  <CheckCircleIcon className="w-5 h-5 text-gray-600" />
                  <h2 className="text-2xl font-semibold text-gray-900">Completed Revisions</h2>
                </div>
              </CardHeader>
              <CardBody className="p-4">
                <div className="space-y-2">
                  {[...completedRuns]
                    .sort((a, b) => new Date(b.completedAt).getTime() - new Date(a.completedAt).getTime())
                    .slice((completedRunsPage - 1) * itemsPerPage, completedRunsPage * itemsPerPage)
                    .map((completed) => {
                    // Determine status color (simplified - just for border)
                    const getStatusColor = () => {
                      if (completed.score > completed.threshold) {
                        return "border-l-4 border-l-green-500"
                      } else if (completed.score <= completed.threshold - 20) {
                        return "border-l-4 border-l-red-500"
                      } else {
                        return "border-l-4 border-l-orange-500"
                      }
                    }
                    
                    return (
                      <div key={completed.runId} className={`border border-gray-200 rounded-lg p-4 bg-white ${getStatusColor()}`}>
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h3 className="font-semibold text-base text-gray-900">{completed.revisionName}</h3>
                            <Chip size="sm" variant="flat" className="mt-1">
                              {completed.subject}
                            </Chip>
                            <div className="mt-2 flex items-center gap-4 text-sm text-gray-600">
                              <span><strong>Score:</strong> {completed.score.toFixed(1)}%</span>
                              <span><strong>Threshold:</strong> {completed.threshold}%</span>
                              <span><strong>Questions:</strong> {completed.totalQuestions}</span>
                              <span className="text-gray-500 text-xs">
                                {new Date(completed.completedAt).toLocaleDateString()}
                              </span>
                            </div>
                          </div>
                          <Button
                            onClick={() => handleViewSummary(completed.runId)}
                            size="sm"
                            className="ml-4 bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all"
                          >
                            View Summary
                          </Button>
                        </div>
                      </div>
                    )
                  })}
                </div>
                {completedRuns.length > itemsPerPage && (
                  <div className="flex justify-center mt-4">
                    <Pagination
                      total={Math.ceil(completedRuns.length / itemsPerPage)}
                      page={completedRunsPage}
                      onChange={setCompletedRunsPage}
                      color="warning"
                      classNames={{
                        wrapper: "gap-0",
                        base: "gap-0",
                        item: "w-8 h-8 text-sm rounded-lg border-2 border-orange-200 bg-white hover:bg-orange-50 data-[selected=true]:bg-gradient-to-r data-[selected=true]:from-orange-600 data-[selected=true]:to-cyan-600 data-[selected=true]:text-white data-[selected=true]:border-orange-400",
                        cursor: "hidden",
                        prev: "rounded-lg border-2 border-orange-200 bg-white hover:bg-orange-50",
                        next: "rounded-lg border-2 border-orange-200 bg-white hover:bg-orange-50",
                      }}
                    />
                  </div>
                )}
              </CardBody>
            </Card>
          )}
        </div>
      )}

      {/* Prep Check Configuration Page */}
      {currentPage === 'prep-check' && prepCheckState === 'config' && (
        <div className="mb-6">
          <div className="mb-4">
            <h2 className="text-2xl font-semibold text-gray-900 mb-1">Check my Prep</h2>
            <p className="text-sm text-gray-600">
              Upload your prep work and get AI feedback on quality, without revealing correct answers
            </p>
          </div>
          <Card className="border border-gray-200 shadow-sm bg-white">
            <CardBody className="p-6">
              <div className="space-y-4 w-full">
                <Select
                  label="Subject"
                  placeholder="Select a subject"
                  selectedKeys={prepCheckForm.subject ? [prepCheckForm.subject] : []}
                  onSelectionChange={(keys) => {
                    const selected = Array.from(keys)[0] as string
                    setPrepCheckForm({ ...prepCheckForm, subject: selected || '' })
                  }}
                  required
                  variant="bordered"
                  classNames={selectClassNames}
                >
                  {subjects.map((subject) => (
                    <SelectItem 
                      key={subject}
                      classNames={{
                        base: "border-2 border-orange-200 rounded-md px-3 py-1.5 flex-shrink-0 whitespace-nowrap min-h-0 h-auto leading-tight data-[hover=true]:bg-orange-100 data-[hover=true]:border-orange-400 data-[selected=true]:bg-orange-50",
                      }}
                    >
                      {subject}
                    </SelectItem>
                  ))}
                </Select>
                
                {previousPrepChecks.length > 0 && (
                  <Select
                    label="Update Previous Prep Check (Optional)"
                    placeholder="Select a previous prep check to update"
                    selectedKeys={prepCheckForm.previousPrepCheckId ? [prepCheckForm.previousPrepCheckId] : []}
                    onSelectionChange={(keys) => {
                      const selected = Array.from(keys)[0] as string | null
                      setPrepCheckForm({ ...prepCheckForm, previousPrepCheckId: selected === 'none' ? null : (selected || null) })
                    }}
                    variant="bordered"
                    classNames={selectClassNames}
                  >
                    {[
                      <SelectItem 
                        key="none"
                        classNames={{
                          base: "border-2 border-orange-200 rounded-md px-3 py-1.5 flex-shrink-0 whitespace-nowrap min-h-0 h-auto leading-tight data-[hover=true]:bg-orange-100 data-[hover=true]:border-orange-400 data-[selected=true]:bg-orange-50",
                        }}
                      >
                        New Prep Check
                      </SelectItem>,
                      ...previousPrepChecks.map((check) => (
                        <SelectItem 
                          key={check.id}
                          classNames={{
                            base: "border-2 border-orange-200 rounded-md px-3 py-1.5 flex-shrink-0 whitespace-nowrap min-h-0 h-auto leading-tight data-[hover=true]:bg-orange-100 data-[hover=true]:border-orange-400 data-[selected=true]:bg-orange-50",
                          }}
                        >
                          {check.subject} - {new Date(check.createdAt).toLocaleDateString()}
                        </SelectItem>
                      ))
                    ]}
                  </Select>
                )}

                <Textarea
                  label="Additional Criteria (Optional)"
                  placeholder="Specify any additional criteria that should be applied when checking the work (e.g., 'Focus on showing work for calculations', 'Check for evidence in answers')"
                  value={prepCheckForm.description}
                  onChange={(e) => {
                    setPrepCheckForm({ ...prepCheckForm, description: e.target.value })
                  }}
                  variant="bordered"
                  minRows={3}
                  classNames={inputClassNames}
                />
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <PhotoIcon className="w-3.5 h-3.5 inline mr-1 text-orange-600" />
                    Upload Files - Images or PDFs of your prep work
                  </label>
                  <div className="space-y-2">
                    <input
                      type="file"
                      accept="image/jpeg,image/jpg,image/png,image/gif,image/webp,.pdf"
                      multiple
                      onChange={(e) => {
                        const files = Array.from(e.target.files || [])
                        const MAX_SIZE = 50 * 1024 * 1024 // 50MB
                        const validFiles: File[] = []
                        const invalidFiles: string[] = []
                        
                        files.forEach((file) => {
                          if (file.size > MAX_SIZE) {
                            invalidFiles.push(`${file.name} (${(file.size / (1024 * 1024)).toFixed(1)}MB)`)
                          } else {
                            validFiles.push(file)
                          }
                        })
                        
                        if (validFiles.length > 0) {
                          setPrepCheckFiles((prev) => {
                            const combined = [...prev, ...validFiles]
                            const unique = combined.filter((file, index, self) =>
                              index === self.findIndex((f) => f.name === file.name && f.size === file.size)
                            )
                            return unique
                          })
                          // Clear any previous errors when valid files are added
                          if (invalidFiles.length === 0) {
                            setError(null)
                          }
                        }
                        
                        if (invalidFiles.length > 0) {
                          setError(`Files too large (max 50MB): ${invalidFiles.join(', ')}`)
                        }
                        
                        // Reset the input value to allow selecting the same file again
                        e.target.value = ''
                      }}
                      className="hidden"
                      id="prep-check-file-input"
                    />
                    <label
                      htmlFor="prep-check-file-input"
                      className="cursor-pointer inline-flex items-center gap-2 px-4 py-2 border-2 border-orange-200 rounded-lg hover:border-orange-400 transition-colors text-gray-700"
                    >
                      <PhotoIcon className="w-4 h-4" />
                      <span>Choose Files</span>
                    </label>
                    {typeof navigator !== 'undefined' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && (
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            const stream = await navigator.mediaDevices.getUserMedia({ video: true })
                            // For now, we'll use a simple approach: create a video element and capture
                            // In a real implementation, you might want a more sophisticated camera UI
                            const video = document.createElement('video')
                            video.srcObject = stream
                            video.play()
                            
                            // Create a canvas to capture the photo
                            const canvas = document.createElement('canvas')
                            const ctx = canvas.getContext('2d')
                            
                            video.addEventListener('loadedmetadata', () => {
                              canvas.width = video.videoWidth
                              canvas.height = video.videoHeight
                              ctx?.drawImage(video, 0, 0)
                              
                              canvas.toBlob((blob) => {
                                if (blob) {
                                  const file = new File([blob], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' })
                                  setPrepCheckFiles((prev) => [...prev, file])
                                }
                                stream.getTracks().forEach(track => track.stop())
                              }, 'image/jpeg', 0.9)
                            })
                          } catch (err) {
                            setError('Failed to access camera. Please ensure camera permissions are granted.')
                          }
                        }}
                        className="inline-flex items-center gap-2 px-4 py-2 border-2 border-cyan-200 rounded-lg hover:border-cyan-400 transition-colors text-gray-700 ml-2"
                      >
                        <PhotoIcon className="w-4 h-4" />
                        <span>Take Photo</span>
                      </button>
                    )}
                  </div>
                  {prepCheckFiles.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {prepCheckFiles.map((file, idx) => (
                        <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded border border-gray-200">
                          <div className="flex items-center gap-2">
                            <DocumentIcon className="w-4 h-4 text-gray-500" />
                            <span className="text-sm text-gray-700">{file.name}</span>
                            <span className="text-xs text-gray-500">
                              ({(file.size / 1024).toFixed(1)} KB)
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              setPrepCheckFiles(prepCheckFiles.filter((_, i) => i !== idx))
                            }}
                            className="text-red-600 hover:text-red-800"
                          >
                            <XMarkIcon className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex gap-3 pt-4">
                  <Button
                    type="button"
                    onClick={handleBackToHome}
                    variant="flat"
                    className="border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 rounded-lg font-semibold transition-all"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    onClick={handleSubmitPrepCheck}
                    disabled={
                      !prepCheckForm.subject?.trim() || 
                      (prepCheckFiles.length === 0 && !prepCheckForm.description?.trim()) || 
                      isCheckingPrep
                    }
                    className="bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    isLoading={isCheckingPrep}
                  >
                    Check my Prep
                  </Button>
                </div>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {/* Prep Check Loading Screen */}
      {currentPage === 'prep-check' && prepCheckState === 'checking' && (
        <div className="mb-6">
          <Card className="bg-gradient-to-r from-yellow-50 to-orange-50 border-2 border-orange-200 rounded-lg">
            <CardBody className="flex flex-col items-center justify-center py-12">
              <Logo size="xl" className="mb-4 animate-pulse" />
              <div className="text-6xl mb-4 animate-spin">⏳</div>
              <p className="text-xl font-semibold text-orange-800 mb-2">Hang on!</p>
              <p className="text-gray-600 text-center mb-6">
                AI is checking your work...
              </p>
              <div className="flex space-x-2">
                <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse"></div>
                <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
                <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {/* Prep Check Results Screen */}
      {currentPage === 'prep-check' && prepCheckState === 'results' && prepCheckResult && (
        <div className="mb-6">
          <div className="mb-4">
            <h2 className="text-2xl font-semibold text-gray-900 mb-1">Prep Check Results</h2>
            <p className="text-sm text-gray-600">
              AI feedback on your prep work
            </p>
          </div>
          <Card className="border border-gray-200 shadow-sm bg-white">
            <CardBody className="p-6">
              <div className="prose prose-sm max-w-none prose-headings:text-gray-900 prose-h1:text-2xl prose-h1:font-semibold prose-h1:mb-4 prose-h2:text-xl prose-h2:font-semibold prose-h2:mt-6 prose-h2:mb-3 prose-h3:text-lg prose-h3:font-semibold prose-h3:mt-4 prose-h3:mb-2 prose-p:text-gray-800 prose-p:leading-relaxed prose-p:mb-3 prose-ul:list-disc prose-ul:pl-6 prose-ul:mb-4 prose-ul:text-gray-800 prose-li:mb-1 prose-strong:text-gray-900 prose-strong:font-semibold prose-ol:list-decimal prose-ol:pl-6 prose-ol:mb-4 prose-ol:text-gray-800">
                <ReactMarkdown
                  components={{
                    h1: ({node, ...props}) => <h1 className="text-2xl font-semibold text-gray-900 mb-4 mt-6 first:mt-0" {...props} />,
                    h2: ({node, ...props}) => <h2 className="text-xl font-semibold text-gray-900 mb-3 mt-6 first:mt-0" {...props} />,
                    h3: ({node, ...props}) => <h3 className="text-lg font-semibold text-gray-900 mb-2 mt-4 first:mt-0" {...props} />,
                    p: ({node, ...props}) => <p className="text-gray-800 leading-relaxed mb-3" {...props} />,
                    ul: ({node, ...props}) => <ul className="list-disc pl-6 mb-4 text-gray-800" {...props} />,
                    ol: ({node, ...props}) => <ol className="list-decimal pl-6 mb-4 text-gray-800" {...props} />,
                    li: ({node, ...props}) => <li className="mb-1" {...props} />,
                    strong: ({node, ...props}) => <strong className="font-semibold text-gray-900" {...props} />,
                    em: ({node, ...props}) => <em className="italic" {...props} />,
                  }}
                >
                  {prepCheckResult}
                </ReactMarkdown>
              </div>
              <div className="mt-6 flex gap-3 justify-end">
                <Button
                  onClick={() => {
                    setPrepCheckForm({
                      subject: prepCheckForm.subject,
                      description: prepCheckForm.description,
                      previousPrepCheckId: prepCheckId,
                    })
                    setPrepCheckFiles([])
                    setPrepCheckResult(null)
                    setPrepCheckState('config')
                    loadPreviousPrepChecks()
                  }}
                  variant="flat"
                  className="border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 rounded-lg font-semibold transition-all"
                >
                  Upload Updated Version
                </Button>
                <Button
                  onClick={handleBackToHome}
                  className="bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all"
                >
                  Done
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {/* Revision Creation Page */}
      {currentPage === 'create' && !revision && !summary && (
        <div className="mb-6">
          <div className="mb-4">
            <h2 className="text-2xl font-semibold text-gray-900 mb-1">Create New Revision</h2>
            <p className="text-sm text-gray-600">
              Set up a revision session with questions tailored to your study materials
            </p>
          </div>
          <Card className="border border-gray-200 shadow-sm bg-white">
            <CardBody className="p-6">
              <form onSubmit={handleCreateRevision} className="space-y-4 w-full">
                <Input
                  label="Revision Name"
                  placeholder="e.g., Math Test Prep"
                  value={form.name}
                  onChange={(e) => {
                    onChangeForm('name', e.target.value)
                    if (formErrors.name) setFormErrors({...formErrors, name: undefined})
                  }}
                  required
                  variant="bordered"
                  isInvalid={!!formErrors.name}
                  errorMessage={formErrors.name}
                  classNames={{
                    ...inputClassNames,
                    inputWrapper: formErrors.name 
                      ? "rounded-lg border-2 border-red-400 hover:border-red-500" 
                      : inputClassNames.inputWrapper,
                  }}
                />
                <Select
                  label="Subject"
                  placeholder="Select a subject"
                  selectedKeys={form.subject ? [form.subject] : []}
                  onSelectionChange={(keys) => {
                    const selected = Array.from(keys)[0] as string
                    onChangeForm('subject', selected || '')
                    if (formErrors.subject) setFormErrors({...formErrors, subject: undefined})
                  }}
                  required
                  variant="bordered"
                  isInvalid={!!formErrors.subject}
                  errorMessage={formErrors.subject}
                  classNames={{
                    ...selectClassNames,
                    trigger: formErrors.subject
                      ? "rounded-lg border-2 border-red-400 hover:border-red-500 px-3 min-h-unit-12"
                      : selectClassNames.trigger,
                  }}
                >
                  {subjects.map((subject) => (
                    <SelectItem 
                      key={subject}
                      classNames={{
                        base: "border-2 border-orange-200 rounded-md px-3 py-1.5 flex-shrink-0 whitespace-nowrap min-h-0 h-auto leading-tight data-[hover=true]:bg-orange-100 data-[hover=true]:border-orange-400 data-[selected=true]:bg-orange-50",
                      }}
                    >
                      {subject}
                    </SelectItem>
                  ))}
                </Select>
                <Select
                  label="Question Style"
                  placeholder="Select question style"
                  selectedKeys={form.questionStyle ? [form.questionStyle] : []}
                  onSelectionChange={(keys) => {
                    const selected = Array.from(keys)[0] as string
                    onChangeForm('questionStyle', (selected || 'free-text') as 'free-text' | 'multiple-choice')
                  }}
                  variant="bordered"
                  classNames={selectClassNames}
                >
                  <SelectItem 
                    key="free-text"
                    classNames={{
                      base: "border-2 border-orange-200 rounded-md px-3 py-1.5 flex-shrink-0 whitespace-nowrap min-h-0 h-auto leading-tight data-[hover=true]:bg-orange-100 data-[hover=true]:border-orange-400 data-[selected=true]:bg-orange-50",
                    }}
                  >
                    Free Text
                  </SelectItem>
                  <SelectItem 
                    key="multiple-choice"
                    classNames={{
                      base: "border-2 border-orange-200 rounded-md px-3 py-1.5 flex-shrink-0 whitespace-nowrap min-h-0 h-auto leading-tight data-[hover=true]:bg-orange-100 data-[hover=true]:border-orange-400 data-[selected=true]:bg-orange-50",
                    }}
                  >
                    Multiple Choice
                  </SelectItem>
                </Select>
                <Textarea
                  label="Description"
                  placeholder="Describe what to study, or upload images with text below"
                  value={form.description}
                  onChange={(e) => {
                    onChangeForm('description', e.target.value)
                    if (formErrors.description) setFormErrors({...formErrors, description: undefined})
                  }}
                  variant="bordered"
                  minRows={3}
                  isInvalid={!!formErrors.description}
                  errorMessage={formErrors.description}
                  classNames={{
                    ...inputClassNames,
                    inputWrapper: formErrors.description
                      ? "rounded-lg border-2 border-red-400 hover:border-red-500"
                      : inputClassNames.inputWrapper,
                  }}
                />
                
                <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  <PhotoIcon className="w-3.5 h-3.5 inline mr-1 text-orange-600" />
                  Upload Files - Images, PDFs, PowerPoint (multiple files supported, text will be extracted automatically)
                </label>
                <input
                  type="file"
                  accept="image/jpeg,image/jpg,image/png,image/gif,image/webp,.pdf,.ppt,.pptx"
                  multiple
                  onChange={(e) => {
                    const files = Array.from(e.target.files || [])
                    const MAX_SIZE = 50 * 1024 * 1024 // 50MB (backend will compress/process as needed)
                    const validFiles: File[] = []
                    const invalidFiles: string[] = []
                    
                    files.forEach((file) => {
                      if (file.size > MAX_SIZE) {
                        invalidFiles.push(`${file.name} (${(file.size / (1024 * 1024)).toFixed(1)}MB)`)
                      } else {
                        validFiles.push(file)
                      }
                    })
                    
                    // Add new files to existing selection (allow adding more files)
                    setSelectedFiles((prev) => {
                      const combined = [...prev, ...validFiles]
                      // Remove duplicates by name
                      const unique = combined.filter((file, index, self) =>
                        index === self.findIndex((f) => f.name === file.name && f.size === file.size)
                      )
                      return unique
                    })
                    if (invalidFiles.length > 0) {
                      setError(`Files too large (max 50MB): ${invalidFiles.join(', ')}`)
                    }
                  }}
                  className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-gradient-to-r file:from-orange-50 file:to-yellow-50 file:text-orange-700 hover:file:from-orange-100 hover:file:to-yellow-100 file:border-2 file:border-orange-200"
                />
                {selectedFiles.length > 0 && (
                  <div className="mt-3 p-3 bg-gradient-to-r from-cyan-50 to-orange-50 rounded-lg border-2 border-cyan-200">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm text-gray-700 font-semibold">
                        {selectedFiles.length} file{selectedFiles.length !== 1 ? 's' : ''} selected
                      </p>
                      <button
                        type="button"
                        onClick={() => setSelectedFiles([])}
                        className="text-xs text-gray-600 hover:text-gray-800 underline rounded-lg px-2 py-1 transition-all cursor-pointer"
                      >
                        Clear all
                      </button>
                    </div>
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {selectedFiles.map((file, index) => {
                        const fileName = file.name.toLowerCase()
                        const isImage = fileName.match(/\.(jpg|jpeg|png|gif|webp)$/)
                        const isPDF = fileName.endsWith('.pdf')
                        const isPPT = fileName.match(/\.(ppt|pptx)$/)
                        
                        let FileIcon = DocumentIcon
                        let iconColor = "text-cyan-600"
                        if (isImage) {
                          FileIcon = PhotoIcon
                          iconColor = "text-cyan-600"
                        } else if (isPDF) {
                          FileIcon = DocumentIcon
                          iconColor = "text-gray-600"
                        } else if (isPPT) {
                          FileIcon = PresentationChartBarIcon
                          iconColor = "text-orange-600"
                        }
                        
                        return (
                          <div
                            key={`${file.name}-${index}`}
                            className="flex items-center justify-between p-2 bg-white rounded border border-gray-200"
                          >
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <FileIcon className={`w-4 h-4 ${iconColor} flex-shrink-0`} />
                              <span className="text-xs text-gray-700 truncate" title={file.name}>
                                {file.name}
                              </span>
                              <span className="text-xs text-gray-500 flex-shrink-0">
                                ({(file.size / 1024).toFixed(0)}KB)
                              </span>
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
                              }}
                              className="ml-2 p-1 hover:bg-red-50 rounded-lg text-red-600 hover:text-red-800 flex-shrink-0 transition-all cursor-pointer"
                              title="Remove file"
                            >
                              <XMarkIcon className="w-4 h-4" />
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
                <p className="text-xs text-gray-500 mt-1">
                  Supported formats: Images (JPEG, PNG, GIF, WebP), PDFs, PowerPoint (PPT, PPTX). 
                  Maximum file size: 50MB per file (images will be automatically compressed if needed). 
                  You can select multiple files at once or add more files.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Input
                  type="number"
                  label="Desired Number of Questions"
                  min={1}
                  value={String(form.desiredQuestionCount)}
                  onChange={(e) =>
                    onChangeForm('desiredQuestionCount', Number(e.target.value))
                  }
                  variant="bordered"
                  classNames={inputClassNames}
                />
                <Input
                  type="number"
                  label="Accuracy Threshold (%)"
                  min={0}
                  max={100}
                  value={String(form.accuracyThreshold)}
                  onChange={(e) =>
                    onChangeForm('accuracyThreshold', Number(e.target.value))
                  }
                  variant="bordered"
                  classNames={inputClassNames}
                />
              </div>

              {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-300 rounded">
                  <p className="text-sm text-red-800 font-medium">{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={isCreating || isProcessingFiles}
                className="w-full rounded-lg font-semibold bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white shadow-md py-3 px-4 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {isProcessingFiles
                  ? 'Processing images and creating...'
                  : isCreating
                  ? 'Creating...'
                  : 'Create Revision'}
        </button>
              </form>
            </CardBody>
          </Card>
        </div>
      )}

      {revision && !summary && (
        <div className="mb-6">
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-300 rounded">
              <p className="text-sm text-red-800 font-medium">{error}</p>
            </div>
          )}

          {isStartingRun || (!question && run && totalQuestions === 0) ? (
            // Loading screen before test starts
            <Card className="bg-gradient-to-r from-yellow-50 to-orange-50 border-2 border-orange-200 rounded-lg">
              <CardBody className="flex flex-col items-center justify-center py-12">
                <Logo size="xl" className="mb-4 animate-pulse" />
                <div className="text-6xl mb-4 animate-spin">⏳</div>
                <p className="text-xl font-semibold text-orange-800 mb-2">Hang on!</p>
                <p className="text-gray-600 text-center mb-6">
                  We're generating your revision questions...
                </p>
                <div className="flex space-x-2">
                  <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse"></div>
                  <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
                  <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
                </div>
              </CardBody>
            </Card>
          ) : question ? (
                <div className="space-y-4">
                  {question.text.startsWith('ERROR:') ? (
                    <Card className="border border-orange-300 shadow-sm bg-white">
                      <CardBody className="p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <XCircleIcon className="w-5 h-5 text-orange-600" />
                          <h3 className="text-lg font-semibold text-orange-900">Error Generating Questions</h3>
                        </div>
                        <p className="text-orange-800 text-base">{question.text.replace('ERROR: ', '')}</p>
                      </CardBody>
                    </Card>
                  ) : (
                    <Card className="border border-gray-200 shadow-sm bg-white">
                      <CardBody className="p-4">
                        {/* Compact stepper at top */}
                        {totalQuestions > 0 && (
                          <div className="mb-3 pb-3 border-b border-gray-200">
                            <div className="flex items-center justify-between">
                              <span className="text-sm font-medium text-gray-700">
                                Question {currentQuestionNumber} of {totalQuestions}
                              </span>
                              <span className="text-xs text-gray-500">
                                {revision.name} • {revision.subject}
                              </span>
                            </div>
                            <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                              <div 
                                className="bg-orange-500 h-1.5 rounded-full transition-all duration-300"
                                style={{ width: `${(currentQuestionNumber / totalQuestions) * 100}%` }}
                              ></div>
                            </div>
                          </div>
                        )}
                        <div className="flex items-start justify-between mb-3">
                          <h3 className="text-2xl font-semibold text-gray-900">Question</h3>
                          <Button
                            size="sm"
                            variant="flat"
                            className="flex-shrink-0 border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 rounded-lg font-semibold transition-all"
                            startContent={<FlagIcon className="w-4 h-4" />}
                            onPress={() => setFlagModal({isOpen: true, questionId: question.id})}
                          >
                            Flag
                          </Button>
                        </div>
                        <p className="text-gray-800 text-base leading-relaxed">{question.text}</p>
                      </CardBody>
                    </Card>
                  )}

                    {/* Answer section - shown when no result yet */}
                    {!lastResult && (
                      <div className="space-y-4">
                        {question.questionStyle === 'multiple-choice' && question.options ? (
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-3">
                              Select your answer:
                            </label>
                            <div className="space-y-2">
                              {question.options.map((option, index) => {
                                const optionLetter = String.fromCharCode(65 + index) // A, B, C, D
                                const isSelected = answer === optionLetter || answer === String(index) || answer === option
                                return (
                                  <button
                                    key={index}
                                    type="button"
                                    onClick={() => {
                                      setAnswer(optionLetter)
                                      if (answerError) setAnswerError(null)
                                    }}
                                    className={`w-full text-left p-4 rounded-lg border-2 transition-all ${
                                      isSelected
                                        ? 'border-orange-500 bg-orange-50 shadow-md'
                                        : 'border-gray-300 bg-white hover:border-orange-300 hover:bg-orange-50'
                                    }`}
                                  >
                                    <div className="flex items-center gap-3">
                                      <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center font-semibold ${
                                        isSelected
                                          ? 'bg-orange-600 text-white'
                                          : 'bg-gray-200 text-gray-700'
                                      }`}>
                                        {optionLetter}
                                      </div>
                                      <span className="text-gray-800">{option}</span>
                                    </div>
                                  </button>
                                )
                              })}
                            </div>
                            {answerError && (
                              <p className="mt-2 text-sm text-red-600">{answerError}</p>
                            )}
                          </div>
                        ) : (
                          <Textarea
                            label="Your Answer"
                            placeholder="Type your answer here... (Press Enter to submit, Shift+Enter for new line)"
                            value={answer}
                            onChange={(e) => {
                              setAnswer(e.target.value)
                              if (answerError) setAnswerError(null)
                            }}
                            onKeyDown={(e) => {
                              // Submit on Enter (but not Shift+Enter, which creates a new line)
                              if (e.key === 'Enter' && !e.shiftKey && answer.trim() && !isSubmittingAnswer) {
                                e.preventDefault()
                                handleSubmitAnswer()
                              }
                            }}
                            variant="bordered"
                            minRows={4}
                            isInvalid={!!answerError}
                            errorMessage={answerError}
                            classNames={{
                              ...inputClassNames,
                              inputWrapper: answerError
                                ? "rounded-lg border-2 border-red-400 hover:border-red-500"
                                : inputClassNames.inputWrapper,
                            }}
                          />
                        )}

                        <Button
                          onClick={handleSubmitAnswer}
                          color="primary"
                          size="lg"
                          className="w-full rounded-lg font-semibold bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white shadow-md transition-all"
                          isLoading={isSubmittingAnswer}
                          disabled={isSubmittingAnswer || !answer.trim()}
                        >
                          {isSubmittingAnswer ? 'Evaluating...' : 'Submit Answer'}
                        </Button>
                      </div>
                    )}

                    {/* Feedback section - replaces answer section when result exists */}
                    {lastResult && (
                      <Card className={`border shadow-sm ${
                        lastResult.error 
                          ? 'border-orange-300 bg-orange-50' 
                          : lastResult.score === 'Full Marks'
                          ? 'border-green-300 bg-green-50'
                          : lastResult.score === 'Partial Marks'
                          ? 'border-yellow-300 bg-yellow-50'
                          : 'border-red-300 bg-red-50'
                      }`}>
                        <CardBody className="p-4">
                          {lastResult.error ? (
                            <div className="space-y-2">
                              <div className="flex items-center gap-2">
                                <XCircleIcon className="w-5 h-5 text-orange-600" />
                                <h4 className="text-lg font-semibold text-orange-800">
                                  Error Marking Answer
                                </h4>
                              </div>
                              <p className="text-sm text-orange-800">
                                {lastResult.error}
                              </p>
                            </div>
                          ) : (
                            <div className="space-y-3">
                              <div className="flex items-center gap-3">
                                {lastResult.score === 'Full Marks' ? (
                                  <div className="flex items-center gap-2">
                                    <CheckCircleIcon className="w-6 h-6 text-green-600" />
                                    <h4 className="text-lg font-semibold text-green-800">
                                      Correct
                                    </h4>
                                  </div>
                                ) : lastResult.score === 'Partial Marks' ? (
                                  <div className="flex items-center gap-2">
                                    <ExclamationTriangleIcon className="w-6 h-6 text-yellow-600" />
                                    <h4 className="text-lg font-semibold text-yellow-800">
                                      Partial Credit
                                    </h4>
                                  </div>
                                ) : (
                                  <div className="flex items-center gap-2">
                                    <XCircleIcon className="w-6 h-6 text-red-600" />
                                    <h4 className="text-lg font-semibold text-red-800">
                                      Incorrect
                                    </h4>
                                  </div>
                                )}
                              </div>
                              <div className="space-y-2">
                                <p className="text-sm text-gray-700">
                                  <span className="font-medium">Correct answer:</span>{' '}
                                  <span className="font-semibold text-gray-900">{lastResult.correctAnswer}</span>
                                </p>
                                {lastResult.explanation && (
                                  <div className="p-3 bg-white rounded border border-gray-200">
                                    <p className="text-sm text-gray-700">
                                      <span className="font-medium">Explanation:</span> {lastResult.explanation}
                                    </p>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                          <div className="flex gap-2 mt-4 pt-4 border-t border-gray-200">
                            <Button
                              onClick={handleNextQuestion}
                              color="primary"
                              className={`flex-1 rounded-lg font-semibold bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white shadow-md transition-all ${buttonWithIconClassName}`}
                              isLoading={isLoadingQuestion}
                              endContent={!isLoadingQuestion && <ArrowRightIcon className="w-4 h-4" />}
                            >
                              Next Question
                            </Button>
                            <Button
                              onPress={handleFinishEarly}
                              color="secondary"
                              variant="flat"
                              className="flex-none px-4 rounded-lg font-semibold border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 transition-all"
                              startContent={<FlagIcon className="w-4 h-4" />}
                            >
                              Finish Now
                            </Button>
                          </div>
                        </CardBody>
                      </Card>
                    )}
                  </div>
                ) : totalQuestions > 0 ? (
                  // Loading screen while summarizing results
                  <Card className="bg-gradient-to-r from-yellow-50 to-orange-50 border-2 border-orange-200 rounded-lg">
                    <CardBody className="flex flex-col items-center justify-center py-12">
                      <Logo size="xl" className="mb-4 animate-pulse" />
                      <div className="text-6xl mb-4 animate-spin">⏳</div>
                      <p className="text-xl font-semibold text-orange-800 mb-2">Hang on!</p>
                      <p className="text-gray-600 text-center mb-6">
                        We're summarizing results...
                      </p>
                      <div className="flex space-x-2">
                        <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse"></div>
                        <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
                        <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
                      </div>
                    </CardBody>
                  </Card>
                ) : (
                  // Loading screen before test starts
                  <Card className="bg-gradient-to-r from-yellow-50 to-orange-50 border-2 border-orange-200 rounded-lg">
                    <CardBody className="flex flex-col items-center justify-center py-12">
                      <Logo size="xl" className="mb-4 animate-pulse" />
                      <div className="text-6xl mb-4 animate-spin">⏳</div>
                      <p className="text-xl font-semibold text-orange-800 mb-2">Hang on!</p>
                      <p className="text-gray-600 text-center mb-6">
                        We're generating your revision questions...
                      </p>
                      <div className="flex space-x-2">
                        <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse"></div>
                        <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
                        <div className="w-3 h-3 bg-orange-500 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
                      </div>
                    </CardBody>
                  </Card>
                )}
          </div>
      )}

      {/* Flag Question Modal - shown when flagging a question */}
      {flagModal.isOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={() => setFlagModal({isOpen: false, questionId: null})}>
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-semibold text-gray-900">Flag Question</h3>
                <button
                  onClick={() => setFlagModal({isOpen: false, questionId: null})}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <XMarkIcon className="w-5 h-5" />
                </button>
              </div>
              <p className="text-gray-600 mb-4">Why are you flagging this question?</p>
              <div className="space-y-2">
                {['incorrect', 'not on topic', "haven't studied material", 'poorly formulated'].map((flagType) => (
                  <button
                    key={flagType}
                    onClick={async () => {
                      if (!run || !flagModal.questionId) return
                      setIsSubmittingFlag(true)
                      try {
                        const token = await getToken()
                        await flagQuestion(run.id, flagModal.questionId, flagType, token)
                        setFlagModal({isOpen: false, questionId: null})
                        // Show success message briefly
                        setError(null)
                      } catch (err: any) {
                        setError(err.message ?? 'Failed to flag question')
                      } finally {
                        setIsSubmittingFlag(false)
                      }
                    }}
                    disabled={isSubmittingFlag}
                    className="w-full text-left p-3 rounded-lg border-2 border-gray-200 hover:border-orange-300 hover:bg-orange-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="text-gray-800 capitalize">{flagType}</span>
                  </button>
                ))}
              </div>
              <div className="mt-4 flex justify-end">
                <Button
                  size="sm"
                  variant="flat"
                  onPress={() => setFlagModal({isOpen: false, questionId: null})}
                  className="border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 rounded-lg font-semibold transition-all"
                >
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Summary page - shown when viewing from completed revisions or after finishing a run */}
      {summary && (
        <div className="mb-6">
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-300 rounded">
              <p className="text-sm text-red-800 font-medium">{error}</p>
            </div>
          )}
          <div className="space-y-4">
            <h2 className="text-2xl font-semibold text-gray-900 mb-2">Summary</h2>
            <Card className="bg-gradient-to-r from-orange-500 via-red-600 to-orange-600 text-white rounded-lg shadow-md border-2 border-orange-300">
              <CardBody>
                <div className="mb-2">
                  <h3 className="text-2xl font-bold">Summary</h3>
                </div>
                <p className="text-3xl font-bold">
                  Overall Accuracy: {summary.overallAccuracy.toFixed(1)}%
                </p>
              </CardBody>
            </Card>

            <Table 
              aria-label="Answer summary"
              classNames={{
                wrapper: "border border-gray-200 rounded-lg shadow-sm",
                th: "bg-gray-50 text-gray-700 font-semibold border-b border-gray-200",
                td: "border-b border-gray-100",
              }}
            >
              <TableHeader>
                <TableColumn className="text-right">#</TableColumn>
                <TableColumn>Question</TableColumn>
                <TableColumn>Your Answer</TableColumn>
                <TableColumn>Correct Answer</TableColumn>
                <TableColumn>Result</TableColumn>
              </TableHeader>
              <TableBody>
                {summary.questions.map((q, idx) => {
                  const rowBgColor = q.score === 'Full Marks' 
                    ? 'bg-green-50' 
                    : q.score === 'Partial Marks'
                    ? 'bg-yellow-50'
                    : 'bg-red-50'
                  return (
                    <TableRow 
                      key={q.questionId} 
                      className={rowBgColor}
                    >
                      <TableCell className="text-right font-medium">{idx + 1}</TableCell>
                      <TableCell className="max-w-md">
                        <p className="text-sm text-gray-800 line-clamp-3">{q.questionText || `Question ${idx + 1}`}</p>
                      </TableCell>
                      <TableCell className="max-w-md">
                        <p className="text-sm text-gray-700 line-clamp-3">{q.studentAnswer || 'No answer provided'}</p>
                      </TableCell>
                      <TableCell className="max-w-md">
                        <p className="text-sm font-semibold text-gray-900 line-clamp-3">{q.correctAnswer}</p>
                      </TableCell>
                      <TableCell>
                        <Chip
                          color={
                            q.score === 'Full Marks' 
                              ? 'success' 
                              : q.score === 'Partial Marks'
                              ? 'warning'
                              : 'danger'
                          }
                          variant="flat"
                          size="sm"
                        >
                          {q.score || (q.isCorrect ? 'Correct' : 'Incorrect')}
                        </Chip>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
      </div>
      
      {/* Confirmation Modal for Delete */}
      {deleteConfirm.isOpen && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center">
          <div 
            className="fixed inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setDeleteConfirm({isOpen: false, revisionId: null})}
          />
          <div className="relative z-[10000] bg-white rounded-lg border-2 border-orange-200 shadow-xl max-w-md w-full mx-4">
            <div className="p-6">
              <div className="flex items-center gap-2 mb-4">
                <ExclamationTriangleIcon className="w-6 h-6 text-orange-600" />
                <h3 className="text-xl font-semibold text-gray-900">Confirm Deletion</h3>
              </div>
              <p className="text-gray-700 mb-6">
                Are you sure you want to delete this revision? This action cannot be undone.
              </p>
              <div className="flex gap-3 justify-end">
                <Button
                  variant="flat"
                  onPress={() => setDeleteConfirm({isOpen: false, revisionId: null})}
                  className="border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 rounded-lg font-semibold transition-all"
                >
                  Cancel
                </Button>
                <Button
                  onPress={async () => {
                    await confirmDeleteRevision()
                  }}
                  className="bg-gradient-to-r from-red-600 to-orange-600 hover:from-red-700 hover:to-orange-700 text-white rounded-lg font-semibold shadow-md transition-all"
                >
                  Delete
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
