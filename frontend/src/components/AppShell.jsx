import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, UserRound, Video, CalendarClock, Users, FolderKanban, FileBarChart, Settings, LogOut,
  KanbanSquare, Sparkles, Menu, X, Search,
} from 'lucide-react'
import { api } from '../api'
import { useUser, useSetUser, isManager } from '../user'
import CommandMenu from './CommandMenu'
import { Avatar, cx } from './ui'

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-8 w-8 items-center justify-center rounded-md border-2 border-ink-950 bg-pop-yellow shadow-press">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="#111" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4 10-11" /></svg>
      </div>
      <div className="leading-tight">
        <p className="text-sm font-bold text-ink-950">MeetPact</p>
        <p className="text-[11px] font-medium text-ink-600">AI notetaker · MeetStream</p>
      </div>
    </div>
  )
}

export default function AppShell({ children }) {
  const user = useUser()
  const setUser = useSetUser()
  const { pathname } = useLocation()
  const [drawer, setDrawer] = useState(false)
  const [palette, setPalette] = useState(false)
  const manager = isManager(user)
  const nav = [
    manager && ['/', 'Team overview', LayoutDashboard],
    user.employee_id && [manager ? '/me' : '/', 'My progress', UserRound],
    ['/board', 'Work board', KanbanSquare],
    ['/ask', 'Ask & search', Sparkles],
    ['/meetings', 'Meetings', Video],
    ['/schedules', 'Schedules', CalendarClock],
    ['/people', manager ? 'People' : 'My team', Users],
    ['/projects', 'Projects', FolderKanban],
    ['/reports', 'Reports', FileBarChart],
    ['/admin', manager ? 'Admin' : 'Settings', Settings],
  ].filter(Boolean)

  // Close the mobile drawer on navigation; Ctrl/Cmd+K opens the command menu.
  useEffect(() => { setDrawer(false) }, [pathname])
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette((p) => !p) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const signOut = async () => {
    await api.logout()
    setUser(null)
    window.location.href = '/'
  }

  const sidebar = (
    <>
      <div className="px-3 pb-3 pt-1">
        <button onClick={() => setPalette(true)}
          className="flex w-full items-center gap-2 rounded-md border-2 border-ink-950 bg-white px-3 py-1.5 text-sm font-medium text-ink-600 shadow-press transition-shadow hover:shadow-card">
          <Search className="h-4 w-4 shrink-0" strokeWidth={2.25} /><span className="whitespace-nowrap">Search</span>
          <kbd className="ml-auto whitespace-nowrap rounded border border-ink-950 bg-ink-100 px-1 font-mono text-[10px]">Ctrl K</kbd>
        </button>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3">
        {nav.map(([to, label, Icon]) => (
          <NavLink key={to + label} to={to} end={to === '/'}
            className={({ isActive }) => cx('flex items-center gap-2.5 rounded-md border-2 px-3 py-1.5 text-sm font-bold transition-[background-color,box-shadow] duration-150 focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500',
              isActive ? 'border-ink-950 bg-pop-yellow text-ink-950 shadow-press' : 'border-transparent text-ink-800 hover:border-ink-950 hover:bg-white')}>
            <Icon className="h-4 w-4" strokeWidth={2.25} />{label}
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center gap-2.5 border-t-2 border-ink-950 px-4 py-3">
        <Avatar name={user.name} />
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-sm font-bold">{user.name}</p>
          <p className="text-[11px] capitalize text-ink-500">{user.role}</p>
        </div>
        <button onClick={signOut} title="Sign out" aria-label="Sign out" className="rounded-md border-2 border-transparent p-1.5 text-ink-950 hover:border-ink-950 hover:bg-pop-pink"><LogOut className="h-4 w-4" /></button>
      </div>
    </>
  )

  return (
    <div className="min-h-[100dvh] lg:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:border-2 focus:border-ink-950 focus:bg-pop-yellow focus:px-3 focus:py-2 focus:text-sm focus:font-bold focus:shadow-card">Skip to content</a>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b-2 border-ink-950 bg-ink-50 px-4 py-3 lg:hidden">
        <Logo />
        <div className="flex gap-2">
          <button onClick={() => setPalette(true)} aria-label="Search" className="rounded-md border-2 border-ink-950 bg-white p-1.5 shadow-press"><Search className="h-4 w-4" /></button>
          <button onClick={() => setDrawer(true)} aria-label="Open menu" className="rounded-md border-2 border-ink-950 bg-pop-yellow p-1.5 shadow-press"><Menu className="h-4 w-4" /></button>
        </div>
      </header>

      {/* Mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-ink-950/50" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r-2 border-ink-950 bg-ink-50">
            <div className="flex items-center justify-between px-4 py-4"><Logo />
              <button onClick={() => setDrawer(false)} aria-label="Close menu" className="rounded-md border-2 border-ink-950 bg-white p-1"><X className="h-4 w-4" /></button>
            </div>
            {sidebar}
          </aside>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-[100dvh] w-60 shrink-0 flex-col border-r-2 border-ink-950 bg-ink-50 lg:flex">
        <div className="px-5 py-5"><Logo /></div>
        {sidebar}
      </aside>

      <main id="main" tabIndex={-1} className="min-w-0 flex-1 px-4 pb-12 pt-6 focus:outline-none sm:px-6 lg:px-8 lg:pt-8">
        <div key={pathname} className="mx-auto max-w-6xl animate-fade-up">{children}</div>
      </main>
      <CommandMenu open={palette} onClose={() => setPalette(false)} nav={nav} />
    </div>
  )
}
