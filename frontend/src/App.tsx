import { useState, useEffect } from 'react'
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
} from '@heroui/react'
import {
  DocumentTextIcon,
  PhotoIcon,
  CheckCircleIcon,
  XCircleIcon,
  XMarkIcon,
  DocumentIcon,
  PresentationChartBarIcon,
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
  uploadedFiles?: string[] | null
  extractedTextPreview?: string | null
}

type Question = {
  id: string
  text: string
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
  return data ? { id: data.id, text: data.text } : null
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
  const [currentPage, setCurrentPage] = useState<'home' | 'create'>('home')
  const [form, setForm] = useState({
    name: '',
    subject: '',
    description: '',
    desiredQuestionCount: 10,
    accuracyThreshold: 80,
  })
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [isProcessingFiles, setIsProcessingFiles] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Shared styling for all Input and Textarea components - Calculator color scheme
  const inputClassNames = {
    label: "mb-2 ml-3 text-orange-600",
    input: "rounded-lg ml-2 pr-2 mb-2 mt-2 text-gray-700",
    inputWrapper: "rounded-lg border-2 border-orange-200 hover:border-orange-400 pr-4",
    placeholder: "ml-3 text-gray-400"
  }

  // Styling for Select dropdown to match Input components - Calculator color scheme
  const selectClassNames = {
    label: "mb-2 ml-3 text-orange-600",
    trigger: "rounded-lg border-2 border-orange-200 hover:border-orange-400 pr-4 min-h-unit-12",
    value: "ml-2 pr-2 text-gray-700",
    popoverContent: "rounded-lg border-2 border-orange-200 bg-white shadow-lg p-3 max-w-full",
    listbox: "bg-white flex flex-wrap gap-2 max-w-full",
    listboxItem: "bg-white text-gray-900 min-h-0 h-auto",
  }

  // Subjects list (loaded from backend)
  const [subjects, setSubjects] = useState<string[]>([])
  const [question, setQuestion] = useState<Question | null>(null)
  const [answer, setAnswer] = useState('')
  const [lastResult, setLastResult] = useState<AnswerResult | null>(null)
  const [isSubmittingAnswer, setIsSubmittingAnswer] = useState(false)
  const [summary, setSummary] = useState<RevisionSummary | null>(null)
  const [totalQuestions, setTotalQuestions] = useState<number>(0)
  const [currentQuestionNumber, setCurrentQuestionNumber] = useState<number>(0)
  const [isLoadingQuestion, setIsLoadingQuestion] = useState(false)

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

  const handleDeleteRevision = async (revisionId: string) => {
    if (!isAuthenticated) {
      setError('You must be logged in to delete revisions')
      return
    }
    if (!confirm('Are you sure you want to delete this revision? This action cannot be undone.')) {
      return
    }
    try {
      setError(null)
      const token = await getToken()
      await deleteRevision(revisionId, token)
      // Reload revisions after deletion
      await loadRevisions()
      await loadCompletedRuns()
    } catch (err: any) {
      setError(err.message ?? 'Failed to delete revision')
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

  const onChangeForm = (field: keyof typeof form, value: string | number) => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleCreateRevision = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
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
        },
        selectedFiles.length > 0 ? selectedFiles : undefined,
        token
      )
      setRevision(created)

      // Start a run for this revision and load the first question
      if (created.id) {
        const newRun = await startRun(created.id, token)
        setRun(newRun)
        setShowRevisionList(false)

        // Get total question count and set initial question number
        const total = await getQuestionCount(newRun.id, token)
        setTotalQuestions(total)
        setCurrentQuestionNumber(1)

        const q = await getNextQuestion(newRun.id, token)
        setQuestion(q)
        setAnswer('')
        setLastResult(null)
        setSummary(null)
        await loadRevisions()
        await loadCompletedRuns()
        // Navigate away from create page (will show run page automatically)
        setCurrentPage('home')
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
    if (!run || !question || !answer.trim()) return
    setIsSubmittingAnswer(true)
    setError(null)
    try {
      const token = await getToken()
      const res = await submitAnswer(run.id, question.id, answer, token)
      setLastResult(res)
    } catch (err: any) {
      setError(err.message ?? 'Failed to submit answer')
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
    if (!isAuthenticated) {
      setError('You must be logged in to finish and view summaries')
      return
    }
    try {
      const token = await getToken()
      const s = await getRunSummary(run.id, token)
      setSummary(s)
      setQuestion(null)
      setAnswer('')
      setLastResult(null)
      // Reload completed runs after finishing
      await loadCompletedRuns()
    } catch (err: any) {
      setError(err.message ?? 'Failed to load summary')
    }
  }

  const handleLaunchRevision = async (revisionId: string) => {
    try {
      setError(null)
      const token = await getToken()
      const newRun = await startRun(revisionId, token)
      const rev = knownRevisions.find(r => r.id === revisionId)
      if (rev) {
        setRevision(rev)
        setRun(newRun)
        setShowRevisionList(false)
        // Load question count and first question
        const count = await getQuestionCount(newRun.id, token)
        setTotalQuestions(count)
        setCurrentQuestionNumber(1)
        const q = await getNextQuestion(newRun.id, token)
        setQuestion(q)
      }
    } catch (err: any) {
      setError(err.message ?? 'Failed to start revision')
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
    setTotalQuestions(0)
    setShowRevisionList(true)
    setCurrentPage('home')
  }

  const handleLoadSummary = async () => {
    if (!run) return
    if (!isAuthenticated) {
      // Non-authenticated users shouldn't see summaries
      return
    }
    try {
      const token = await getToken()
      const s = await getRunSummary(run.id, token)
      setSummary(s)
    } catch (err: any) {
      setError(err.message ?? 'Failed to load summary')
    }
  }

  // Auto-load summary when no more questions (only for authenticated users)
  useEffect(() => {
    if (run && !question && !summary && totalQuestions > 0 && isAuthenticated) {
      // Small delay to show animation
      const timer = setTimeout(() => {
        handleLoadSummary()
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [run, question, summary, totalQuestions, isAuthenticated])

  // Load revisions and completed runs on mount and when auth state changes
  useEffect(() => {
    if (!authLoading) {
      loadRevisions()
      loadCompletedRuns()
      setShowRevisionList(true)
    }
  }, [authLoading, isAuthenticated])

  // Load revisions and completed runs on mount and when auth state changes
  useEffect(() => {
    if (!authLoading) {
      loadRevisions()
      loadCompletedRuns()
      setShowRevisionList(true)
    }
  }, [authLoading, isAuthenticated])

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
      {/* Authentication Banner */}
      {!isAuthenticated && import.meta.env.VITE_AUTH0_DOMAIN && (
        <div className="bg-gradient-to-r from-yellow-50 via-amber-50 to-orange-50 border-l-4 border-yellow-400 p-4 mb-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-yellow-700">
                  <strong>Session-only mode:</strong> Your revisions and progress will not be saved after you close this page.{' '}
                  <button 
                    onClick={login}
                    className="font-medium underline hover:text-yellow-900 rounded-lg px-2 py-1 transition-all"
                  >
                    Sign in to save your work
                  </button>
                </p>
              </div>
            </div>
            <button
              onClick={login}
              className="ml-4 bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white px-4 py-2 rounded-lg font-semibold shadow-md transition-all"
            >
              Sign In
            </button>
          </div>
        </div>
      )}
      
      {isAuthenticated && user && (
        <div className="bg-gradient-to-r from-green-50 via-emerald-50 to-cyan-50 border-l-4 border-green-400 p-3 mb-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {user.picture && (
                <img src={user.picture} alt={user.name || user.email} className="w-8 h-8 rounded-full" />
              )}
              <span className="text-sm text-green-800">
                Signed in as <strong>{user.name || user.email}</strong> - Your work is being saved
              </span>
            </div>
            <button
              onClick={logout}
              className="text-sm text-green-700 hover:text-green-900 underline rounded-lg px-2 py-1 transition-all"
            >
              Sign Out
            </button>
          </div>
        </div>
      )}

      <div className="max-w-6xl ml-8 mr-auto px-4 py-8">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-2">
            <Logo size="lg" />
            <h1 className="text-4xl font-bold text-blue-600">
              My Revision Pal
            </h1>
          </div>
          <p className="text-blue-400">AI-powered study companion for effective learning</p>
        </div>

      {/* Revision Lists View (Homepage) */}
      {currentPage === 'home' && showRevisionList && !revision && !summary && (
        <div className="space-y-6">
          {/* Create New Revision Card */}
          <Card className="rounded-xl border-2 border-orange-100 shadow-lg cursor-pointer hover:shadow-xl transition-all hover:border-orange-400" onClick={() => setCurrentPage('create')}>
            <CardHeader className="bg-gradient-to-r from-orange-50 to-yellow-50 rounded-t-xl">
              <div className="flex items-center gap-3">
                <DocumentTextIcon className="w-6 h-6 text-orange-600" />
                <h2 className="text-2xl font-semibold text-orange-900">Create New Revision</h2>
              </div>
            </CardHeader>
            <CardBody className="p-6">
              <div className="flex items-center justify-between">
                <p className="text-gray-700">
                  Set up a new revision session with questions tailored to your study materials
                </p>
                <Button
                  color="primary"
                  size="md"
                  className="ml-4 bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all"
                  onClick={(e) => {
                    e.stopPropagation()
                    setCurrentPage('create')
                  }}
                >
                  Create
                </Button>
              </div>
            </CardBody>
          </Card>

          {/* Configured Revisions */}
          {knownRevisions.length > 0 && (
            <Card className="rounded-xl border-2 border-orange-100 shadow-lg">
              <CardHeader className="bg-gradient-to-r from-orange-50 to-yellow-50 rounded-t-xl">
                <div className="flex items-center gap-3">
                  <DocumentTextIcon className="w-6 h-6 text-orange-600" />
                  <h2 className="text-2xl font-semibold text-orange-900">Configured Revisions</h2>
                </div>
              </CardHeader>
              <CardBody>
                <div className="space-y-3">
                  {knownRevisions.map((r) => (
                    <Card key={r.id} className="border-2 border-orange-200 hover:shadow-lg transition-all hover:border-orange-400 rounded-lg bg-gradient-to-r from-yellow-50 to-cyan-50">
                      <CardBody>
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h3 className="font-semibold text-lg text-gray-900">{r.name}</h3>
                            <Chip size="sm" variant="flat" color="secondary" className="mt-1 rounded-full">
                              {r.subject}
                            </Chip>
                            {r.uploadedFiles && r.uploadedFiles.length > 0 && (
                              <div className="flex items-center gap-1 mt-2 text-sm text-gray-600">
                                <PhotoIcon className="w-3 h-3 text-cyan-600" />
                                <span>Files: {r.uploadedFiles.join(', ')}</span>
                              </div>
                            )}
                            {r.extractedTextPreview && (
                              <p className="text-sm text-gray-500 italic mt-2 line-clamp-2">
                                "{r.extractedTextPreview}"
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            <Button
                              onClick={() => r.id && handleLaunchRevision(r.id)}
                              color="primary"
                              size="md"
                              className="bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white rounded-lg font-semibold shadow-md transition-all"
                              isDisabled={!r.id}
                            >
                              Start
                            </Button>
                            {isAuthenticated && r.id && (
                              <Button
                                onClick={() => r.id && handleDeleteRevision(r.id)}
                                color="danger"
                                size="md"
                                variant="flat"
                                className="bg-gradient-to-r from-red-50 to-rose-50 hover:from-red-100 hover:to-rose-100 border-2 border-red-300 text-red-700 rounded-lg font-semibold shadow-md transition-all"
                              >
                                Delete
                              </Button>
                            )}
                          </div>
                        </div>
                      </CardBody>
                    </Card>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}

          {/* Completed Revisions - Only show for authenticated users */}
          {isAuthenticated && completedRuns.length > 0 && (
            <Card className="rounded-xl border-2 border-green-100 shadow-lg">
              <CardHeader className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-t-xl">
                <div className="flex items-center gap-3">
                  <CheckCircleIcon className="w-6 h-6 text-green-600" />
                  <h2 className="text-2xl font-semibold text-green-900">Completed Revisions</h2>
                </div>
              </CardHeader>
              <CardBody>
                <div className="space-y-3">
                  {completedRuns.map((completed) => (
                    <Card key={completed.runId} className="border-2 border-green-200 hover:shadow-lg transition-all hover:border-green-400 rounded-lg bg-gradient-to-r from-green-50 to-cyan-50">
                      <CardBody>
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h3 className="font-semibold text-lg text-gray-900">{completed.revisionName}</h3>
                            <Chip size="sm" variant="flat" color="success" className="mt-1 rounded-full">
                              {completed.subject}
                            </Chip>
                            <div className="mt-2 flex items-center gap-4 text-sm">
                              <span className="text-gray-700">
                                <strong>Score:</strong> {completed.score.toFixed(1)}%
                              </span>
                              <span className="text-gray-600">
                                <strong>Questions:</strong> {completed.totalQuestions}
                              </span>
                              <span className="text-gray-500 text-xs">
                                {new Date(completed.completedAt).toLocaleDateString()}
                              </span>
                            </div>
                          </div>
                          <Button
                            onClick={() => handleViewSummary(completed.runId)}
                            color="success"
                            size="md"
                            className="ml-4 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white rounded-lg font-semibold shadow-md transition-all"
                          >
                            View Summary
                          </Button>
                        </div>
                      </CardBody>
                    </Card>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}

          {/* Show message if no revisions */}
          {knownRevisions.length === 0 && completedRuns.length === 0 && (
            <Card className="rounded-xl border-2 border-gray-200 shadow-lg bg-white">
              <CardBody className="text-center py-8">
                <DocumentTextIcon className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">No revisions yet. Click the button above to create one!</p>
              </CardBody>
            </Card>
          )}
        </div>
      )}

      {/* Revision Creation Page */}
      {currentPage === 'create' && !revision && !summary && (
        <div className="mb-6">
          <div className="mb-4">
            <Button
              onClick={() => setCurrentPage('home')}
              color="secondary"
              variant="flat"
              className="bg-gradient-to-r from-gray-50 to-slate-50 hover:from-gray-100 hover:to-slate-100 border-2 border-gray-300 text-gray-700 rounded-lg font-semibold shadow-md transition-all"
            >
              ← Back to Home
            </Button>
          </div>
          <Card className="rounded-xl border-2 border-orange-100 shadow-lg bg-white mb-4">
            <CardBody className="p-6">
              <div className="flex items-start gap-3">
                <DocumentTextIcon className="w-12 h-12 text-orange-600 flex-shrink-0" />
                <div>
                  <h2 className="text-2xl font-semibold text-orange-900 mb-2">Set Up a Revision</h2>
                  <p className="text-sm text-gray-700">
                    Create a new revision session with questions tailored to your study materials
                  </p>
                </div>
              </div>
            </CardBody>
          </Card>
          <div className="rounded-xl border-2 border-orange-100 shadow-lg bg-white p-6">
            <form onSubmit={handleCreateRevision} className="space-y-4 w-full">
              <Input
                label="Revision Name"
                placeholder="e.g., Math Test Prep"
                value={form.name}
                onChange={(e) => onChangeForm('name', e.target.value)}
                required
                variant="bordered"
                classNames={inputClassNames}
              />
              <Select
                label="Subject"
                placeholder="Select a subject"
                selectedKeys={form.subject ? [form.subject] : []}
                onSelectionChange={(keys) => {
                  const selected = Array.from(keys)[0] as string
                  onChangeForm('subject', selected || '')
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
              <Textarea
                label="Description"
                placeholder="Describe what to study, or upload images with text below"
                value={form.description}
                onChange={(e) => onChangeForm('description', e.target.value)}
                variant="bordered"
                minRows={3}
                classNames={inputClassNames}
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
                      <p className="text-sm text-green-800 font-semibold">
                        {selectedFiles.length} file{selectedFiles.length !== 1 ? 's' : ''} selected
                      </p>
                      <button
                        type="button"
                        onClick={() => setSelectedFiles([])}
                        className="text-xs text-green-700 hover:text-green-900 underline rounded-lg px-2 py-1 transition-all"
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
                          iconColor = "text-green-600"
                        } else if (isPDF) {
                          FileIcon = DocumentIcon
                          iconColor = "text-red-600"
                        } else if (isPPT) {
                          FileIcon = PresentationChartBarIcon
                          iconColor = "text-orange-600"
                        }
                        
                        return (
                          <div
                            key={`${file.name}-${index}`}
                            className="flex items-center justify-between p-2 bg-white rounded border border-green-200"
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
                              className="ml-2 p-1 hover:bg-red-50 rounded-lg text-red-600 hover:text-red-800 flex-shrink-0 transition-all"
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
                <div className="p-3 bg-gradient-to-r from-red-50 to-rose-50 border-2 border-red-300 rounded-lg">
                  <p className="text-sm text-red-800 font-medium">{error}</p>
      </div>
              )}

              <button
                type="submit"
                disabled={isCreating || isProcessingFiles}
                className="w-full rounded-lg font-semibold bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 shadow-lg text-white py-3 px-4 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {isProcessingFiles
                  ? 'Processing images and creating...'
                  : isCreating
                  ? 'Creating...'
                  : 'Create Revision'}
        </button>
            </form>
          </div>
        </div>
      )}

      {revision && (
        <div className="mb-6">
          <div className="mb-4 flex items-start gap-3">
            <Logo size="md" className="flex-shrink-0" />
            <div>
              <h2 className="text-2xl font-semibold text-orange-900 mb-2">Let's Revise!</h2>
              <p className="text-sm text-gray-700">
                <strong className="text-orange-800">{revision.name}</strong> • <span className="text-cyan-700">{revision.subject}</span>
              </p>
            </div>
          </div>
          <div className="rounded-xl border-2 border-orange-100 shadow-lg bg-white p-6">
            {error && (
              <div className="p-3 bg-gradient-to-r from-red-50 to-rose-50 border-2 border-red-300 rounded-lg mb-4">
                <p className="text-sm text-red-800 font-medium">{error}</p>
              </div>
            )}

            {!summary && (
              <>
                {/* Progress Tracker */}
                {totalQuestions > 0 && (
                  <div className="mb-4 p-3 bg-gradient-to-r from-orange-50 to-yellow-50 border-2 border-orange-200 rounded-lg">
                    <p className="text-center text-lg font-semibold text-orange-700">
                      Question {currentQuestionNumber} of {totalQuestions}
                    </p>
                    <div className="mt-2 w-full bg-gradient-to-r from-blue-200 via-cyan-200 to-blue-300 rounded-full h-2.5 shadow-inner">
                      <div 
                        className="bg-gradient-to-r from-orange-500 via-orange-600 to-red-600 h-2.5 rounded-full transition-all duration-300 shadow-sm"
                        style={{ width: `${(currentQuestionNumber / totalQuestions) * 100}%` }}
                      ></div>
                    </div>
                  </div>
                )}

                {question ? (
                  <div className="space-y-4">
                    {question.text.startsWith('ERROR:') ? (
                      <Card className="bg-gradient-to-r from-orange-50 to-amber-50 border-2 border-orange-300 rounded-xl shadow-md">
                        <CardBody>
                          <div className="flex items-center gap-2 mb-2">
                            <XCircleIcon className="w-5 h-5 text-orange-600" />
                            <h3 className="text-lg font-semibold text-orange-900">Error Generating Questions</h3>
                          </div>
                          <p className="text-orange-800 text-base">{question.text.replace('ERROR: ', '')}</p>
                        </CardBody>
                      </Card>
                    ) : (
                      <Card className="bg-gradient-to-r from-cyan-50 to-orange-50 border-2 border-orange-300 rounded-xl shadow-md">
                        <CardBody>
                          <h3 className="text-lg font-semibold mb-2 text-orange-900">
                            Question {totalQuestions > 0 ? `${currentQuestionNumber} of ${totalQuestions}` : ''}
                          </h3>
                          <p className="text-gray-700 text-lg">{question.text}</p>
                        </CardBody>
                      </Card>
                    )}

                    <Textarea
                      label="Your Answer"
                      placeholder="Type your answer here... (Press Enter to submit, Shift+Enter for new line)"
                      value={answer}
                      onChange={(e) => setAnswer(e.target.value)}
                      onKeyDown={(e) => {
                        // Submit on Enter (but not Shift+Enter, which creates a new line)
                        if (e.key === 'Enter' && !e.shiftKey && answer.trim() && !isSubmittingAnswer) {
                          e.preventDefault()
                          handleSubmitAnswer()
                        }
                      }}
                      variant="bordered"
                      minRows={4}
                      classNames={inputClassNames}
                    />

                    <Button
                      onClick={handleSubmitAnswer}
                      color="primary"
                      size="lg"
                      className="w-full rounded-lg font-semibold bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white shadow-lg transition-all"
                      isLoading={isSubmittingAnswer}
                      disabled={isSubmittingAnswer || !answer.trim()}
                    >
                      {isSubmittingAnswer ? 'Checking...' : 'Submit Answer'}
                    </Button>

                    {lastResult && (
                      <Card className={`border-2 rounded-xl shadow-md ${
                        lastResult.error 
                          ? 'border-orange-400 bg-gradient-to-r from-orange-50 to-amber-50' 
                          : lastResult.score === 'Full Marks'
                          ? 'border-cyan-400 bg-gradient-to-r from-cyan-50 to-orange-50'
                          : lastResult.score === 'Partial Marks'
                          ? 'border-yellow-400 bg-gradient-to-r from-yellow-50 to-amber-50'
                          : 'border-red-400 bg-gradient-to-r from-red-50 to-rose-50'
                      }`}>
                        <CardBody>
                          {lastResult.error ? (
                            <div className="space-y-2">
                              <div className="flex items-center gap-2 mb-3">
                                <XCircleIcon className="w-5 h-5 text-orange-600" />
                                <h4 className="text-lg font-semibold text-orange-800">
                                  Error Marking Answer
                                </h4>
                              </div>
                              <div className="mt-3 p-3 bg-white rounded-lg border-2 border-orange-200">
                                <p className="text-sm text-orange-800 font-medium">
                                  {lastResult.error}
                                </p>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="flex items-center gap-2 mb-3">
                                {lastResult.score === 'Full Marks' ? (
                                  <CheckCircleIcon className="w-4 h-4 text-green-600" />
                                ) : lastResult.score === 'Partial Marks' ? (
                                  <CheckCircleIcon className="w-4 h-4 text-yellow-600" />
                                ) : (
                                  <XCircleIcon className="w-4 h-4 text-red-600" />
                                )}
                                <h4 className={`text-lg font-semibold ${
                                  lastResult.score === 'Full Marks' 
                                    ? 'text-green-800' 
                                    : lastResult.score === 'Partial Marks'
                                    ? 'text-yellow-800'
                                    : 'text-red-800'
                                }`}>
                                  {lastResult.score || (lastResult.isCorrect ? 'Correct!' : 'Incorrect')}
                                </h4>
                              </div>
                              <div className="space-y-2">
                                <p className="text-gray-700">
                                  <span className="font-medium">Correct answer:</span>{' '}
                                  <span className="font-semibold text-gray-900">{lastResult.correctAnswer}</span>
                                </p>
                                {lastResult.explanation && (
                                  <div className="mt-3 p-3 bg-white rounded-lg border-2 border-gray-200">
                                    <p className="text-sm text-gray-700">
                                      <span className="font-medium">Explanation:</span> {lastResult.explanation}
        </p>
      </div>
                                )}
                              </div>
                            </>
                          )}
                          <div className="flex gap-2 mt-4">
                            <Button
                              onClick={handleFinishEarly}
                              color="secondary"
                              variant="flat"
                              className="flex-1 rounded-lg font-semibold bg-gradient-to-r from-gray-50 to-slate-50 hover:from-gray-100 hover:to-slate-100 border-2 border-gray-300 text-gray-700 shadow-md transition-all"
                            >
                              Finish Now
                            </Button>
                            <Button
                              onClick={handleNextQuestion}
                              color="primary"
                              variant="flat"
                              className="flex-1 rounded-lg font-semibold bg-gradient-to-r from-orange-600 to-cyan-600 hover:from-orange-700 hover:to-cyan-700 text-white border-2 border-orange-500 shadow-md transition-all"
                              isLoading={isLoadingQuestion}
                            >
                              Next Question
                            </Button>
                          </div>
                        </CardBody>
                      </Card>
                    )}
                  </div>
                ) : totalQuestions > 0 ? (
                  // Animation screen when all questions are completed
                  <Card className="bg-gradient-to-r from-orange-50 to-yellow-50 border-2 border-orange-200 rounded-xl">
                    <CardBody className="flex flex-col items-center justify-center py-12">
                      <Logo size="xl" className="mb-4 animate-bounce" />
                      <div className="text-6xl mb-4 animate-bounce">🎉</div>
                      <p className="text-xl font-semibold text-orange-800 mb-2">Great job!</p>
                      <p className="text-gray-600 text-center mb-6">
                        You've completed all the questions. Loading your summary...
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
                  <Card className="bg-gradient-to-r from-yellow-50 to-orange-50 border-2 border-orange-200 rounded-xl">
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
              </>
            )}

            {summary && isAuthenticated && (
              <div className="space-y-4">
                <div className="flex items-center justify-between mb-4">
                  <Button
                    onClick={handleBackToHome}
                    color="secondary"
                    variant="flat"
                    className="bg-gradient-to-r from-gray-50 to-slate-50 hover:from-gray-100 hover:to-slate-100 border-2 border-gray-300 text-gray-700 rounded-lg font-semibold shadow-md transition-all"
                  >
                    ← Back to Revisions
                  </Button>
                </div>
                <Card className="bg-gradient-to-r from-orange-500 via-red-600 to-orange-600 text-white rounded-xl shadow-xl border-2 border-orange-300">
                  <CardBody>
                    <div className="flex items-center gap-3 mb-2">
                      <Logo size="md" />
                      <h3 className="text-2xl font-bold">Summary</h3>
                    </div>
                    <p className="text-3xl font-bold">
                      Overall Accuracy: {summary.overallAccuracy.toFixed(1)}%
                    </p>
                  </CardBody>
                </Card>

                <Table aria-label="Answer summary">
                  <TableHeader>
                    <TableColumn>#</TableColumn>
                    <TableColumn>Question</TableColumn>
                    <TableColumn>Your Answer</TableColumn>
                    <TableColumn>Correct Answer</TableColumn>
                    <TableColumn>Result</TableColumn>
                  </TableHeader>
                  <TableBody>
                    {summary.questions.map((q, idx) => {
                      const rowColorClass = q.score === 'Full Marks' 
                        ? 'bg-gradient-to-r from-green-50 via-emerald-50 to-green-100 hover:from-green-100 hover:via-emerald-100 hover:to-green-200' 
                        : q.score === 'Partial Marks'
                        ? 'bg-gradient-to-r from-yellow-50 via-amber-50 to-yellow-100 hover:from-yellow-100 hover:via-amber-100 hover:to-yellow-200'
                        : 'bg-gradient-to-r from-red-50 via-rose-50 to-red-100 hover:from-red-100 hover:via-rose-100 hover:to-red-200'
                      return (
                        <TableRow 
                          key={q.questionId} 
                          className={rowColorClass}
                          style={{
                            backgroundColor: q.score === 'Full Marks' 
                              ? '#f0fdf4' 
                              : q.score === 'Partial Marks'
                              ? '#fefce8'
                              : '#fef2f2'
                          }}
                        >
                          <TableCell>{idx + 1}</TableCell>
                          <TableCell className="font-medium">{q.questionText || 'Question not available'}</TableCell>
                          <TableCell>{q.studentAnswer}</TableCell>
                          <TableCell className="font-semibold">{q.correctAnswer}</TableCell>
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
            )}
          </div>
        </div>
      )}
      </div>
    </div>
  )
}

export default App
