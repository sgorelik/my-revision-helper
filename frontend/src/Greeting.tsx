import { useState, useEffect } from 'react'
import { Spinner } from '@heroui/react'

type GreetingState =
  | { status: 'loading' }
  | { status: 'success'; message: string }
  | { status: 'error'; error: string }

export default function Greeting() {
  const [state, setState] = useState<GreetingState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/hello', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Server responded with status ${res.status}`)
        }
        return res.json()
      })
      .then((data: { message: string }) => {
        setState({ status: 'success', message: data.message })
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        const errorMessage =
          err instanceof Error ? err.message : 'Unknown error'
        setState({
          status: 'error',
          error: errorMessage,
        })
      })

    return () => controller.abort()
  }, [])

  return (
    <div className="flex items-center justify-center min-h-[120px] w-full px-4">
      {state.status === 'loading' && (
        <div
          role="status"
          className="flex flex-col items-center gap-2"
        >
          <Spinner size="lg" />
          <p className="text-gray-500 text-sm">Loading greeting…</p>
        </div>
      )}

      {state.status === 'success' && (
        <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold text-center text-gray-800">
          {state.message}
        </h1>
      )}

      {state.status === 'error' && (
        <div
          role="alert"
          className="text-center text-red-600 bg-red-50 border border-red-200 rounded-lg p-4 max-w-md"
        >
          <p className="font-semibold">Could not load greeting</p>
          <p className="text-sm mt-1">{state.error}</p>
        </div>
      )}
    </div>
  )
}
