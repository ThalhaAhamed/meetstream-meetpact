import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
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
import Setup from './pages/Setup'

export default function App() {
  const [state, setState] = useState({ loading: true, needsSetup: false, user: null })

  useEffect(() => {
    // If the server is restarting, keep retrying instead of showing the sign-in page.
    let stop = false
    const load = (attempt = 0) => api.authState()
      .then((s) => !stop && setState({ loading: false, needsSetup: s.needs_setup, user: s.user }))
      .catch(() => {
        if (stop) return
        if (attempt < 20) { setState((s) => ({ ...s, offline: attempt >= 1 })); setTimeout(() => load(attempt + 1), 1500) }
        else setState({ loading: false, needsSetup: false, user: null })
      })
    load()
    return () => { stop = true }
  }, [])

  const navigate = useNavigate()
  const setUser = (user) => {
    if (state.needsSetup && user) navigate('/setup')  // the first admin goes straight to the setup guide
    setState((s) => ({ ...s, user, needsSetup: false }))
  }

  if (state.loading) return <Spinner inline label={state.offline ? 'Reconnecting to the MeetPact server…' : 'Loading…'} />
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
          <Route path="/setup" element={state.user.role === 'admin' ? <Setup /> : <Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </UserContext.Provider>
  )
}
