import { useState } from 'react'
import './App.css'

type RevisionConfig = {
  id?: string
  name: string
  subject: string
  topics: string[]
  description?: string
  desiredQuestionCount: number
  accuracyThreshold: number
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

const API_BASE = 'http://localhost:8000/api'

async function createRevision(config: RevisionConfig): Promise<RevisionConfig> {
  const formData = new FormData()
  formData.append('name', config.name)
  formData.append('subject', config.subject)
  formData.append('description', config.description ?? '')
  formData.append('desiredQuestionCount', String(config.desiredQuestionCount))
  formData.append('accuracyThreshold', String(config.accuracyThreshold))
  formData.append('topics', JSON.stringify(config.topics))

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
  const [isCreating, setIsCreating] = useState(false)
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
    try {
      const topics = form.topicsInput
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
      const created = await createRevision({
        name: form.name,
        subject: form.subject,
        topics,
        description: form.description,
        desiredQuestionCount: form.desiredQuestionCount,
        accuracyThreshold: form.accuracyThreshold,
      })
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
    } catch (err: any) {
      setError(err.message ?? 'Failed to create revision')
    } finally {
      setIsCreating(false)
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
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '1.5rem' }}>
      <h1>My Revision Helper</h1>

      {knownRevisions.length > 0 && !revision && (
        <section style={{ marginBottom: '2rem' }}>
          <h2>Existing Revisions</h2>
          <ul>
            {knownRevisions.map((r) => (
              <li key={r.id}>
                <strong>{r.name}</strong> ({r.subject})
              </li>
            ))}
          </ul>
        </section>
      )}

      {!revision && (
        <section style={{ marginBottom: '2rem' }}>
          <h2>Set Up a Revision</h2>
          <form onSubmit={handleCreateRevision} style={{ display: 'grid', gap: '0.75rem' }}>
            <label>
              Revision Name
              <input
                type="text"
                value={form.name}
                onChange={(e) => onChangeForm('name', e.target.value)}
                required
              />
            </label>
            <label>
              Subject
              <input
                type="text"
                value={form.subject}
                onChange={(e) => onChangeForm('subject', e.target.value)}
                required
              />
            </label>
            <label>
              Topic Areas (comma-separated)
              <input
                type="text"
                value={form.topicsInput}
                onChange={(e) => onChangeForm('topicsInput', e.target.value)}
                placeholder="Fractions, Algebra, ..."
              />
            </label>
            <label>
              Description
              <textarea
                value={form.description}
                onChange={(e) => onChangeForm('description', e.target.value)}
              />
            </label>
            <label>
              Desired Number of Questions
              <input
                type="number"
                min={1}
                value={form.desiredQuestionCount}
                onChange={(e) =>
                  onChangeForm('desiredQuestionCount', Number(e.target.value))
                }
              />
            </label>
            <label>
              Desired Accuracy Threshold (%)
              <input
                type="number"
                min={0}
                max={100}
                value={form.accuracyThreshold}
                onChange={(e) =>
                  onChangeForm('accuracyThreshold', Number(e.target.value))
                }
              />
            </label>

            {error && <p style={{ color: 'red' }}>{error}</p>}

            <button type="submit" disabled={isCreating}>
              {isCreating ? 'Creating...' : 'Create Revision'}
            </button>
          </form>
        </section>
      )}

      {revision && (
        <section>
          <h2>Run Revision</h2>
          <p>
            Revision: <strong>{revision.name}</strong> ({revision.subject})
          </p>

          {error && <p style={{ color: 'red' }}>{error}</p>}

          {!summary && (
            <>
              {question ? (
                <div style={{ marginTop: '1rem' }}>
                  <h3>Question</h3>
                  <p>{question.text}</p>
                  <textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    rows={4}
                    style={{ width: '100%' }}
                  />
                  <button
                    onClick={handleSubmitAnswer}
                    disabled={isSubmittingAnswer || !answer.trim()}
                    style={{ marginTop: '0.5rem' }}
                  >
                    {isSubmittingAnswer ? 'Checking...' : 'Submit Answer'}
                  </button>

                  {lastResult && (
                    <div style={{ marginTop: '1rem' }}>
                      <p>
                        Result:{' '}
                        <strong
                          style={{
                            color: lastResult.isCorrect ? 'green' : 'red',
                          }}
                        >
                          {lastResult.isCorrect ? 'Correct' : 'Incorrect'}
                        </strong>
                      </p>
                      <p>
                        Correct answer: <strong>{lastResult.correctAnswer}</strong>
                      </p>
                      {lastResult.explanation && (
                        <p>Explanation: {lastResult.explanation}</p>
                      )}
                      <button onClick={handleNextQuestion} style={{ marginTop: '0.5rem' }}>
                        Next Question
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <p>No more questions. You can view your summary.</p>
              )}

              <button onClick={handleLoadSummary} style={{ marginTop: '1rem' }}>
                View Summary
              </button>
            </>
          )}

          {summary && (
            <div style={{ marginTop: '2rem' }}>
              <h3>Summary</h3>
              <p>Overall accuracy: {summary.overallAccuracy.toFixed(1)}%</p>
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Your Answer</th>
                    <th>Correct Answer</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.questions.map((q, idx) => (
                    <tr key={q.questionId}>
                      <td>{idx + 1}</td>
                      <td>{q.studentAnswer}</td>
                      <td>{q.correctAnswer}</td>
                      <td>{q.isCorrect ? 'Correct' : 'Incorrect'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

export default App
