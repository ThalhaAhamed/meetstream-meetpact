import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { UserContext, isManager } from './user'
import AppShell from './components/AppShell'
import { Spinner } from './components/ui'
import SignIn from './pages/SignIn'
import Dashboard from './pages/Dashboard'
import MyProgress from './pages/MyProgress'
import Meetings from './pages/Meetings'
import MeetingDetail from './pages/MeetingDetail'
import Schedules from './pages/Schedules'
import People from './pages/People'
import EmployeeProfile from './pages/EmployeeProfile'
import Projects from './pages/Projects'
import Reports from './pages/Reports'
import Admin from './pages/Admin'
import Board from './pages/Board'
import Ask from './pages/Ask'

export default function App() {
  const [state, setState] = useState({ loading: true, needsSetup: false, user: null })

  useEffect(() => {
    api.authState()
      .then((s) => setState({ loading: false, needsSetup: s.needs_setup, user: s.user }))
      .catch(() => setState({ loading: false, needsSetup: false, user: null }))
  }, [])

  const setUser = (user) => setState((s) => ({ ...s, user, needsSetup: false }))

  if (state.loading) return <Spinner inline />
  if (!state.user) return <SignIn needsSetup={state.needsSetup} onSignedIn={setUser} />

  const home = isManager(state.user) ? <Dashboard /> : <MyProgress />
  return (
    <UserContext.Provider value={{ user: state.user, setUser }}>
      <AppShell>
        <Routes>
          <Route path="/" element={home} />
          <Route path="/team" element={<Dashboard />} />
          <Route path="/me" element={<MyProgress />} />
          <Route path="/meetings" element={<Meetings />} />
          <Route path="/meetings/:id" element={<MeetingDetail />} />
          <Route path="/schedules" element={<Schedules />} />
          <Route path="/people" element={<People />} />
          <Route path="/people/:id" element={<EmployeeProfile />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/board" element={<Board />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </UserContext.Provider>
  )
}
