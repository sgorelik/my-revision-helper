/**
 * Routing for the app.
 *
 * The original single-page revision tool is preserved wholesale at /practice.
 * It owns its own chrome, so it sits outside the shell rather than inside it,
 * and the retest flow hands off to it by revision id.
 */

import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom'

import App from './App'
import { markAuthReady, setTokenGetter } from './api/client'
import { isAuth0Configured, useAuth } from './auth'
import Shell from './components/Shell'
import { ChildProvider, useChildren } from './context/ChildContext'
import AssignmentPage from './pages/AssignmentPage'
import ChildrenPage from './pages/ChildrenPage'
import DashboardPage from './pages/DashboardPage'
import HomePage from './pages/HomePage'
import KidLanding from './pages/KidLanding'
import LibraryPage from './pages/LibraryPage'
import MarkingPage from './pages/MarkingPage'

/**
 * Give the API client a way to fetch the Auth0 token, and tell it when the
 * answer to "who is this?" is finally known.
 *
 * Registered inside the router so it re-registers whenever the auth state
 * changes, keeping the closure's isAuthenticated value current. This sits
 * above the routes but below the provider, so its effect runs before any
 * page's fetch on the same commit.
 */
function AuthBridge() {
  const { getToken, isAuthenticated, isLoading } = useAuth()

  useEffect(() => {
    setTokenGetter(getToken)
    // Without an Auth0Provider isLoading never clears, so an unconfigured
    // build is ready immediately rather than never.
    if (!isAuth0Configured || !isLoading) markAuthReady()
  }, [getToken, isAuthenticated, isLoading])

  return null
}

/** Keep the switcher in step when a child is reached by URL. */
function SyncSelectedChild({ children }: { children: React.ReactNode }) {
  const { childId } = useParams<{ childId: string }>()
  const { selectChild, selectedChild } = useChildren()

  useEffect(() => {
    if (childId && childId !== selectedChild?.id) selectChild(childId)
  }, [childId, selectedChild?.id, selectChild])

  return <>{children}</>
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <ChildProvider>
        <AuthBridge />
        <Routes>
          {/* The original revision and prep-check tool, unchanged. */}
          <Route path="/practice/*" element={<App />} />

          <Route element={<Shell />}>
            <Route index element={<HomePage />} />
            <Route
              path="/kid/:childId"
              element={
                <SyncSelectedChild>
                  <KidLanding />
                </SyncSelectedChild>
              }
            />
            <Route
              path="/dashboard/:childId"
              element={
                <SyncSelectedChild>
                  <DashboardPage />
                </SyncSelectedChild>
              }
            />
            <Route path="/work/:assignmentId" element={<AssignmentPage />} />
            <Route path="/marking/:markingId" element={<MarkingPage />} />
            <Route path="/manage/library" element={<LibraryPage />} />
            <Route path="/manage/children" element={<ChildrenPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </ChildProvider>
    </BrowserRouter>
  )
}
