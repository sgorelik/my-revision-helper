import { useState } from 'react'
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
} from '@heroui/react'
import {
  DocumentTextIcon,
  PhotoIcon,
  CheckCircleIcon,
  XCircleIcon,
  AcademicCapIcon,
  XMarkIcon,
  DocumentIcon,
  PresentationChartBarIcon,
} from '@heroicons/react/24/outline'

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
  studentAnswer: string
  isCorrect: boolean
  correctAnswer: string
  explanation?: string | null
  error?: string | null
}

type RevisionSummary = {
  revisionId: string
  questions: AnswerResult[]
  overallAccuracy: number
}

type RevisionRun = {
  id: string
  revisionId: string
  status: string
}

// API base URL - uses environment variable if set, otherwise defaults to localhost for dev
// When served from same domain (production), use relative path
const API_BASE = import.meta.env.VITE_API_BASE || '/api'

async function createRevision(
  config: RevisionConfig,
  files?: File[]
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

  const res = await fetch(`${API_BASE}/revisions`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    throw new Error('Failed to create revision')
  }
  return res.json()
}

async function listRevisions(): Promise<RevisionConfig[]> {
  const res = await fetch(`${API_BASE}/revisions`)
  if (!res.ok) throw new Error('Failed to load revisions')
  return res.json()
}

async function startRun(revisionId: string): Promise<RevisionRun> {
  const res = await fetch(`${API_BASE}/revisions/${revisionId}/runs`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to start run')
  return res.json()
}

async function getNextQuestion(runId: string): Promise<Question | null> {
  const res = await fetch(`${API_BASE}/runs/${runId}/next-question`)
  if (!res.ok) throw new Error('Failed to load question')
  return res.json()
}

async function submitAnswer(
  runId: string,
  questionId: string,
  answer: string,
): Promise<AnswerResult> {
  const res = await fetch(`${API_BASE}/runs/${runId}/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ questionId, answer }),
  })
  if (!res.ok) throw new Error('Failed to submit answer')
  return res.json()
}

async function getRunSummary(runId: string): Promise<RevisionSummary> {
  const res = await fetch(`${API_BASE}/runs/${runId}/summary`)
  if (!res.ok) throw new Error('Failed to load summary')
  return res.json()
}

function App() {
  const [revision, setRevision] = useState<RevisionConfig | null>(null)
  const [run, setRun] = useState<RevisionRun | null>(null)
  const [knownRevisions, setKnownRevisions] = useState<RevisionConfig[]>([])
  const [form, setForm] = useState({
    name: '',
    subject: '',
    topicsInput: '',
    description: '',
    desiredQuestionCount: 2,
    accuracyThreshold: 80,
  })
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [isProcessingFiles, setIsProcessingFiles] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [question, setQuestion] = useState<Question | null>(null)
  const [answer, setAnswer] = useState('')
  const [lastResult, setLastResult] = useState<AnswerResult | null>(null)
  const [isSubmittingAnswer, setIsSubmittingAnswer] = useState(false)
  const [summary, setSummary] = useState<RevisionSummary | null>(null)

  const loadRevisions = async () => {
    try {
      const revs = await listRevisions()
      setKnownRevisions(revs)
    } catch (err: any) {
      setError(err.message ?? 'Failed to load revisions')
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
      const topics = form.topicsInput
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
      const created = await createRevision(
        {
          name: form.name,
          subject: form.subject,
          topics,
          description: form.description,
          desiredQuestionCount: form.desiredQuestionCount,
          accuracyThreshold: form.accuracyThreshold,
        },
        selectedFiles.length > 0 ? selectedFiles : undefined
      )
      setRevision(created)

      // Start a run for this revision and load the first question
      const newRun = await startRun(created.id!)
      setRun(newRun)

      const q = await getNextQuestion(newRun.id)
      setQuestion(q)
      setAnswer('')
      setLastResult(null)
      setSummary(null)
      await loadRevisions()
      // Clear selected files after successful creation
      setSelectedFiles([])
    } catch (err: any) {
      setError(err.message ?? 'Failed to create revision')
    } finally {
      setIsCreating(false)
      setIsProcessingFiles(false)
    }
  }

  const handleSubmitAnswer = async () => {
    if (!run || !question || !answer.trim()) return
    setIsSubmittingAnswer(true)
    setError(null)
    try {
      const res = await submitAnswer(run.id, question.id, answer)
      setLastResult(res)
    } catch (err: any) {
      setError(err.message ?? 'Failed to submit answer')
    } finally {
      setIsSubmittingAnswer(false)
    }
  }

  const handleNextQuestion = async () => {
    if (!run) return
    try {
      const q = await getNextQuestion(run.id)
      setQuestion(q)
      setAnswer('')
      setLastResult(null)
    } catch (err: any) {
      setError(err.message ?? 'Failed to load next question')
    }
  }

  const handleLoadSummary = async () => {
    if (!run) return
    try {
      const s = await getRunSummary(run.id)
      setSummary(s)
    } catch (err: any) {
      setError(err.message ?? 'Failed to load summary')
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2 flex items-center justify-center gap-2">
            <AcademicCapIcon className="w-5 h-5 text-indigo-600" />
            My Revision Helper
          </h1>
          <p className="text-gray-600">AI-powered study companion for effective learning</p>
        </div>

      {knownRevisions.length > 0 && !revision && (
        <Card className="mb-6 rounded-xl border-2 border-purple-100 shadow-lg">
          <CardHeader className="bg-gradient-to-r from-purple-50 to-pink-50 rounded-t-xl">
            <h2 className="text-2xl font-semibold text-purple-900">Existing Revisions</h2>
          </CardHeader>
          <CardBody>
            <div className="space-y-3">
              {knownRevisions.map((r) => (
                <Card key={r.id} className="border-2 border-blue-200 hover:shadow-lg transition-all hover:border-blue-400 rounded-lg bg-gradient-to-r from-blue-50 to-cyan-50">
                  <CardBody>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-semibold text-lg text-gray-900">{r.name}</h3>
                        <Chip size="sm" variant="flat" color="secondary" className="mt-1 rounded-full">
                          {r.subject}
                        </Chip>
                        {r.uploadedFiles && r.uploadedFiles.length > 0 && (
                          <div className="flex items-center gap-1 mt-2 text-sm text-gray-600">
                            <PhotoIcon className="w-3 h-3 text-blue-600" />
                            <span>Files: {r.uploadedFiles.join(', ')}</span>
                          </div>
                        )}
                        {r.extractedTextPreview && (
                          <p className="text-sm text-gray-500 italic mt-2 line-clamp-2">
                            "{r.extractedTextPreview}"
                          </p>
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

      {!revision && (
        <Card className="mb-6 rounded-xl border-2 border-indigo-100 shadow-lg">
          <CardHeader className="bg-gradient-to-r from-indigo-50 to-blue-50 rounded-t-xl">
            <h2 className="text-2xl font-semibold flex items-center gap-2 text-indigo-900">
              <DocumentTextIcon className="w-4 h-4 text-indigo-600" />
              Set Up a Revision
            </h2>
          </CardHeader>
          <CardBody>
            <form onSubmit={handleCreateRevision} className="space-y-4">
              <Input
                label="Revision Name"
                placeholder="e.g., Math Test Prep"
                value={form.name}
                onChange={(e) => onChangeForm('name', e.target.value)}
                required
                variant="bordered"
                classNames={{
                  input: "rounded-lg",
                  inputWrapper: "rounded-lg border-2 border-indigo-200 hover:border-indigo-400"
                }}
              />
              <Input
                label="Subject"
                placeholder="e.g., Mathematics"
                value={form.subject}
                onChange={(e) => onChangeForm('subject', e.target.value)}
                required
                variant="bordered"
                classNames={{
                  input: "rounded-lg",
                  inputWrapper: "rounded-lg border-2 border-indigo-200 hover:border-indigo-400"
                }}
              />
              <Input
                label="Topic Areas"
                placeholder="Fractions, Algebra, Geometry (comma-separated)"
                value={form.topicsInput}
                onChange={(e) => onChangeForm('topicsInput', e.target.value)}
                variant="bordered"
                description="Separate multiple topics with commas"
                classNames={{
                  input: "rounded-lg",
                  inputWrapper: "rounded-lg border-2 border-indigo-200 hover:border-indigo-400"
                }}
              />
              <Textarea
                label="Description"
                placeholder="Describe what to study, or upload images with text below"
                value={form.description}
                onChange={(e) => onChangeForm('description', e.target.value)}
                variant="bordered"
                minRows={3}
                classNames={{
                  input: "rounded-lg",
                  inputWrapper: "rounded-lg border-2 border-indigo-200 hover:border-indigo-400"
                }}
              />
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  <PhotoIcon className="w-3.5 h-3.5 inline mr-1 text-pink-600" />
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
                  className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-gradient-to-r file:from-pink-50 file:to-purple-50 file:text-pink-700 hover:file:from-pink-100 hover:file:to-purple-100 file:border-2 file:border-pink-200"
                />
                {selectedFiles.length > 0 && (
                  <div className="mt-3 p-3 bg-gradient-to-r from-green-50 to-emerald-50 rounded-lg border-2 border-green-200">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm text-green-800 font-semibold">
                        {selectedFiles.length} file{selectedFiles.length !== 1 ? 's' : ''} selected
                      </p>
                      <button
                        type="button"
                        onClick={() => setSelectedFiles([])}
                        className="text-xs text-green-700 hover:text-green-900 underline"
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
                        let iconColor = "text-blue-600"
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
                              className="ml-2 p-1 hover:bg-red-50 rounded text-red-600 hover:text-red-800 flex-shrink-0"
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
                  classNames={{
                    input: "rounded-lg",
                    inputWrapper: "rounded-lg border-2 border-indigo-200 hover:border-indigo-400"
                  }}
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
                  classNames={{
                    input: "rounded-lg",
                    inputWrapper: "rounded-lg border-2 border-indigo-200 hover:border-indigo-400"
                  }}
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
                className="w-full rounded-lg font-semibold bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 shadow-lg text-white py-3 px-4 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
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
      )}

      {revision && (
        <Card className="rounded-xl border-2 border-emerald-100 shadow-lg">
          <CardHeader className="bg-gradient-to-r from-emerald-50 to-teal-50 rounded-t-xl">
            <div className="flex items-center justify-between w-full">
              <div>
                <h2 className="text-2xl font-semibold text-emerald-900">Run Revision</h2>
                <p className="text-sm text-gray-700 mt-1">
                  <strong className="text-emerald-800">{revision.name}</strong> • <span className="text-teal-700">{revision.subject}</span>
                </p>
              </div>
            </div>
          </CardHeader>
          <CardBody>
            {error && (
              <div className="p-3 bg-gradient-to-r from-red-50 to-rose-50 border-2 border-red-300 rounded-lg mb-4">
                <p className="text-sm text-red-800 font-medium">{error}</p>
              </div>
            )}

            {!summary && (
              <>
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
                      <Card className="bg-gradient-to-r from-indigo-50 to-blue-50 border-2 border-indigo-300 rounded-xl shadow-md">
                        <CardBody>
                          <h3 className="text-lg font-semibold mb-2 text-indigo-900">Question</h3>
                          <p className="text-gray-700 text-lg">{question.text}</p>
                        </CardBody>
                      </Card>
                    )}

                    <Textarea
                      label="Your Answer"
                      placeholder="Type your answer here..."
                      value={answer}
                      onChange={(e) => setAnswer(e.target.value)}
                      variant="bordered"
                      minRows={4}
                      classNames={{
                        input: "rounded-lg",
                        inputWrapper: "rounded-lg border-2 border-emerald-200 hover:border-emerald-400"
                      }}
                    />

                    <Button
                      onClick={handleSubmitAnswer}
                      color="primary"
                      size="lg"
                      className="w-full rounded-lg font-semibold bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 shadow-lg"
                      isLoading={isSubmittingAnswer}
                      disabled={isSubmittingAnswer || !answer.trim()}
                    >
                      {isSubmittingAnswer ? 'Checking...' : 'Submit Answer'}
                    </Button>

                    {lastResult && (
                      <Card className={`border-2 rounded-xl shadow-md ${lastResult.error ? 'border-orange-400 bg-gradient-to-r from-orange-50 to-amber-50' : lastResult.isCorrect ? 'border-green-400 bg-gradient-to-r from-green-50 to-emerald-50' : 'border-red-400 bg-gradient-to-r from-red-50 to-rose-50'}`}>
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
                                {lastResult.isCorrect ? (
                                  <CheckCircleIcon className="w-4 h-4 text-green-600" />
                                ) : (
                                  <XCircleIcon className="w-4 h-4 text-red-600" />
                                )}
                                <h4 className={`text-lg font-semibold ${lastResult.isCorrect ? 'text-green-800' : 'text-red-800'}`}>
                                  {lastResult.isCorrect ? 'Correct!' : 'Incorrect'}
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
                          <Button
                            onClick={handleNextQuestion}
                            color="primary"
                            variant="flat"
                            className="w-full mt-4 rounded-lg font-semibold bg-gradient-to-r from-blue-50 to-indigo-50 hover:from-blue-100 hover:to-indigo-100 border-2 border-blue-200 text-blue-700"
                          >
                            Next Question
                          </Button>
                        </CardBody>
                      </Card>
                    )}
                  </div>
                ) : (
                  <Card className="bg-gradient-to-r from-gray-50 to-slate-50 border-2 border-gray-200 rounded-xl">
                    <CardBody>
                      <p className="text-gray-600 text-center py-4">
                        No more questions. You can view your summary.
                      </p>
                      <Button
                        onClick={handleLoadSummary}
                        color="primary"
                        size="lg"
                        className="w-full rounded-lg font-semibold bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 shadow-lg"
                      >
                        View Summary
                      </Button>
                    </CardBody>
                  </Card>
                )}

                {!question && (
                  <Button
                    onClick={handleLoadSummary}
                    color="primary"
                    size="lg"
                    className="w-full mt-4 rounded-lg font-semibold bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 shadow-lg"
                  >
                    View Summary
                  </Button>
                )}
              </>
            )}

            {summary && (
              <div className="space-y-4">
                <Card className="bg-gradient-to-r from-indigo-500 via-purple-600 to-pink-600 text-white rounded-xl shadow-xl border-2 border-purple-300">
                  <CardBody>
                    <h3 className="text-2xl font-bold mb-2">Summary</h3>
                    <p className="text-3xl font-bold">
                      Overall Accuracy: {summary.overallAccuracy.toFixed(1)}%
                    </p>
                  </CardBody>
                </Card>

                <Table aria-label="Answer summary">
                  <TableHeader>
                    <TableColumn>#</TableColumn>
                    <TableColumn>Your Answer</TableColumn>
                    <TableColumn>Correct Answer</TableColumn>
                    <TableColumn>Result</TableColumn>
                  </TableHeader>
                  <TableBody>
                    {summary.questions.map((q, idx) => (
                      <TableRow key={q.questionId}>
                        <TableCell>{idx + 1}</TableCell>
                        <TableCell>{q.studentAnswer}</TableCell>
                        <TableCell className="font-semibold">{q.correctAnswer}</TableCell>
                        <TableCell>
                          <Chip
                            color={q.isCorrect ? 'success' : 'danger'}
                            variant="flat"
                            size="sm"
                          >
                            {q.isCorrect ? 'Correct' : 'Incorrect'}
                          </Chip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardBody>
        </Card>
      )}
      </div>
    </div>
  )
}

export default App
