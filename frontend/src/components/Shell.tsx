/**
 * The application frame: brand, child switcher, primary navigation.
 */

import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth'
import { useChildren } from '../context/ChildContext'
import { theme } from './ui'

function ChildSwitcher() {
  const { children, selectedChild, selectChild } = useChildren()
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  if (children.length === 0) return null

  const accent = theme(selectedChild?.colour)

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        {selectedChild ? (
          <>
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br text-xs text-white ${accent.gradient}`}
            >
              {selectedChild.avatarEmoji || selectedChild.name.charAt(0)}
            </span>
            {selectedChild.name}
          </>
        ) : (
          'Choose a student'
        )}
        <span className="text-slate-400">▾</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-2 w-56 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
            {children.map((child) => {
              const childAccent = theme(child.colour)
              return (
                <button
                  key={child.id}
                  onClick={() => {
                    selectChild(child.id)
                    setOpen(false)
                    navigate(`/kid/${child.id}`)
                  }}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-slate-50"
                >
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br text-xs text-white ${childAccent.gradient}`}
                  >
                    {child.avatarEmoji || child.name.charAt(0)}
                  </span>
                  <span>
                    <span className="block font-medium text-slate-800">{child.name}</span>
                    {child.yearGroup && (
                      <span className="block text-xs text-slate-500">{child.yearGroup}</span>
                    )}
                  </span>
                </button>
              )
            })}
            <div className="my-1 border-t border-slate-100" />
            <Link
              to="/manage/children"
              onClick={() => setOpen(false)}
              className="block px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
            >
              Manage students
            </Link>
          </div>
        </>
      )}
    </div>
  )
}

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
  }`
}

export default function Shell() {
  const { selectedChild } = useChildren()
  const { isAuthenticated, user, login, logout } = useAuth()

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-bold text-slate-900">
            <span className="text-xl">🎯</span>
            <span className="hidden sm:inline">Revision Helper</span>
          </Link>

          <nav className="ml-4 hidden items-center gap-1 md:flex">
            <NavLink to="/" end className={navClass}>
              Home
            </NavLink>
            {selectedChild && (
              <>
                <NavLink to={`/kid/${selectedChild.id}`} className={navClass}>
                  My work
                </NavLink>
                <NavLink to={`/dashboard/${selectedChild.id}`} className={navClass}>
                  Progress
                </NavLink>
              </>
            )}
            <NavLink to="/manage/library" className={navClass}>
              Library
            </NavLink>
            <NavLink to="/practice" className={navClass}>
              Practice
            </NavLink>
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <ChildSwitcher />
            {isAuthenticated ? (
              <button
                onClick={logout}
                title={user?.email}
                className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
              >
                Sign out
              </button>
            ) : (
              <button
                onClick={login}
                className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
              >
                Sign in
              </button>
            )}
          </div>
        </div>

        {/* Compact nav for small screens */}
        <nav className="flex items-center gap-1 overflow-x-auto border-t border-slate-100 px-4 py-2 md:hidden">
          <NavLink to="/" end className={navClass}>
            Home
          </NavLink>
          {selectedChild && (
            <>
              <NavLink to={`/kid/${selectedChild.id}`} className={navClass}>
                My work
              </NavLink>
              <NavLink to={`/dashboard/${selectedChild.id}`} className={navClass}>
                Progress
              </NavLink>
            </>
          )}
          <NavLink to="/manage/library" className={navClass}>
            Library
          </NavLink>
          <NavLink to="/practice" className={navClass}>
            Practice
          </NavLink>
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
