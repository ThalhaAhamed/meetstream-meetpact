// Every HTTP call the UI makes lives here. Pages never call fetch directly.

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const detail = data && typeof data === 'object' ? data.detail : data
    const message = Array.isArray(detail)
      ? detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ')
      : detail || `Request failed (${res.status})`
    const err = new Error(message)
    err.status = res.status
    throw err
  }
  return data
}

const get = (p) => request('GET', p)
const post = (p, b = {}) => request('POST', p, b)
const put = (p, b) => request('PUT', p, b)
const patch = (p, b) => request('PATCH', p, b)
const del = (p) => request('DELETE', p)
const qs = (o = {}) => {
  const s = new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString()
  return s ? `?${s}` : ''
}

export const api = {
  // auth
  authState: () => get('/api/auth/state'),
  setup: (b) => post('/api/auth/setup', b),
  login: (b) => post('/api/auth/login', b),
  logout: () => post('/api/auth/logout'),

  // dashboards
  dashboard: (team_id) => get('/api/dashboard' + qs({ team_id })),
  myDashboard: () => get('/api/me/dashboard'),
  employeeProfile: (id) => get(`/api/employees/${id}/profile`),
  projectsProgress: () => get('/api/projects/progress'),
  projectItems: (id) => get(`/api/projects/${id}/items`),

  // meetings
  meetings: (params) => get('/api/meetings' + qs(params)),
  meeting: (id) => get(`/api/meetings/${id}`),
  createMeeting: (b) => post('/api/meetings', b),
  importTranscript: (b) => post('/api/meetings/import', b),
  pauseMeeting: (id) => post(`/api/meetings/${id}/pause`),
  resumeMeeting: (id) => post(`/api/meetings/${id}/resume`),
  removeBot: (id) => post(`/api/meetings/${id}/remove`),
  reprocess: (id) => post(`/api/meetings/${id}/reprocess`),
  shareMeeting: (id, b) => put(`/api/meetings/${id}/share`, b),
  mapParticipant: (id, pid, b) => put(`/api/meetings/${id}/participants/${pid}`, b),
  deleteMeeting: (id) => del(`/api/meetings/${id}`),
  reportUrl: (id, employee_id) => `/api/meetings/${id}/report.md` + qs({ employee_id }),

  // schedules
  schedules: () => get('/api/schedules'),
  upcoming: (days = 7) => get('/api/schedules/upcoming' + qs({ days })),
  createSchedule: (b) => post('/api/schedules', b),
  updateSchedule: (id, b) => put(`/api/schedules/${id}`, b),
  deleteSchedule: (id) => del(`/api/schedules/${id}`),

  // progress
  workItems: (params) => get('/api/work-items' + qs(params)),
  workItem: (id) => get(`/api/work-items/${id}`),
  createWorkItem: (b) => post('/api/work-items', b),
  updateWorkItem: (id, b) => patch(`/api/work-items/${id}`, b),
  deleteWorkItem: (id) => del(`/api/work-items/${id}`),
  pushWorkItem: (id, provider) => post(`/api/work-items/${id}/push`, { provider }),
  syncWorkItem: (id) => post(`/api/work-items/${id}/sync`),
  blockers: (status = 'open') => get('/api/blockers' + qs({ status })),
  updateBlocker: (id, b) => patch(`/api/blockers/${id}`, b),
  reviewUpdate: (id, b) => patch(`/api/updates/${id}`, b),
  periodReport: (params) => get('/api/reports/period' + qs(params)),

  // org
  teams: () => get('/api/teams'),
  teamBoard: (id) => get(`/api/teams/${id}/board`),
  chooseBoard: (id, b) => put(`/api/teams/${id}/board`, b),
  moveCard: (id, b) => post(`/api/teams/${id}/board/move`, b),
  linkBoardMember: (id, b) => put(`/api/teams/${id}/board/members`, b),
  trello: () => get('/api/trello'),
  saveTrello: (b) => put('/api/trello', b),
  disconnectTrello: () => del('/api/trello'),
  trelloBoards: () => get('/api/trello/boards'),
  createTeam: (b) => post('/api/teams', b),
  updateTeam: (id, b) => put(`/api/teams/${id}`, b),
  deleteTeam: (id) => del(`/api/teams/${id}`),
  projects: () => get('/api/projects'),
  createProject: (b) => post('/api/projects', b),
  updateProject: (id, b) => put(`/api/projects/${id}`, b),
  deleteProject: (id) => del(`/api/projects/${id}`),
  employees: () => get('/api/employees'),
  directory: () => get('/api/employees/directory'),
  createEmployee: (b) => post('/api/employees', b),
  updateEmployee: (id, b) => put(`/api/employees/${id}`, b),
  deactivateEmployee: (id) => del(`/api/employees/${id}`),
  users: () => get('/api/users'),
  createUser: (b) => post('/api/users', b),
  updateUser: (id, b) => put(`/api/users/${id}`, b),
  deleteUser: (id) => del(`/api/users/${id}`),
  settings: () => get('/api/settings'),
  saveSettings: (b) => put('/api/settings', b),
  setupStatus: () => get('/api/setup'),
  saveSetupKeys: (b) => put('/api/setup/keys', b),
  checkSetup: (what) => post(`/api/setup/check/${what}`),
  finishSetup: () => post('/api/setup/done'),
  voices: () => get('/api/setup/voices'),
  chooseVoice: (b) => put('/api/setup/voices', b),
  checkVoice: () => post('/api/setup/voices/check'),
  testDelivery: (channel) => post('/api/settings/delivery-test', { channel }),
  integrations: () => get('/api/integrations'),
  syncIntegrations: () => post('/api/integrations/sync'),
  checkIntegration: (name) => post(`/api/integrations/${name}/check`),

  // calendar
  calendar: () => get('/api/calendar'),
  connectCalendar: (b) => post('/api/calendar/connect', b),
  disconnectCalendar: () => del('/api/calendar'),
  setCalendarAutoJoin: (b) => put('/api/calendar/auto-join', b),
  calendarEvents: (hours = 72) => get('/api/calendar/events' + qs({ hours })),
  joinCalendarEvent: (id, mode = 'notetaker') => post(`/api/calendar/events/${id}/join`, { mode }),

  // search, ask, privacy, delivery
  search: (q) => get('/api/search' + qs({ q })),
  ask: (question) => post('/api/ask', { question }),
  deleteRecording: (id) => post(`/api/meetings/${id}/delete-recording`),
  deliverReport: (id) => post(`/api/meetings/${id}/deliver`),
  eraseEmployee: (id) => post(`/api/employees/${id}/erase`),
}
