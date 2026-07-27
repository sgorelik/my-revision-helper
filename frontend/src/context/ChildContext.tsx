/**
 * The list of children and which one is currently selected.
 *
 * Kids share the parent's login and switch profiles, so the selected child is
 * app state rather than an identity. It is remembered in localStorage so
 * reopening the app lands on the same kid.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api } from '../api/client'
import type { Child } from '../api/types'

const STORAGE_KEY = 'mrh.selectedChildId'

interface ChildContextValue {
  children: Child[]
  selectedChild: Child | null
  selectChild: (childId: string | null) => void
  reload: () => Promise<void>
  loading: boolean
  error: string | null
}

const ChildContext = createContext<ChildContextValue | null>(null)

export function ChildProvider({ children: reactChildren }: { children: ReactNode }) {
  const [children, setChildren] = useState<Child[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY),
  )
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const items = await api.listChildren()
      setChildren(items)

      // Drop a stale selection, and auto-select when there is only one child.
      setSelectedId((current) => {
        if (current && items.some((c) => c.id === current)) return current
        return items.length === 1 ? items[0].id : null
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load children')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    if (selectedId) localStorage.setItem(STORAGE_KEY, selectedId)
    else localStorage.removeItem(STORAGE_KEY)
  }, [selectedId])

  const value = useMemo<ChildContextValue>(
    () => ({
      children,
      selectedChild: children.find((c) => c.id === selectedId) || null,
      selectChild: setSelectedId,
      reload,
      loading,
      error,
    }),
    [children, selectedId, reload, loading, error],
  )

  return <ChildContext.Provider value={value}>{reactChildren}</ChildContext.Provider>
}

export function useChildren(): ChildContextValue {
  const context = useContext(ChildContext)
  if (!context) throw new Error('useChildren must be used inside a ChildProvider')
  return context
}
