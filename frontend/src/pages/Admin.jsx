import { useEffect, useState } from 'react'
import { CheckCircle2, CircleDashed, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useUser, isManager } from '../user'
import {
  Badge, Button, Card, CardHeader, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, Tabs, Textarea, useLoad,
} from '../components/ui'

const split = (s) => s.split(',').map((x) => x.trim()).filter(Boolean)

// Generic list + modal editor used for employees, teams, projects and users.
function Crud({ title, rows, columns, blank, toForm, fields, onSave, onDelete, deleteLabel = 'Delete' }) {
  const [form, setForm] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true); setError(null)
    try { await onSave(form); setForm(null) } catch (e) { setError(e) } finally { setBusy(false) }
  }
  return (
    <Card>
      <CardHeader title={title} action={<Button size="sm" icon={Plus} onClick={() => { setError(null); setForm(blank()) }}>Add</Button>} />
      <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-sm">
        <thead><tr className="border-b border-ink-100 text-left text-[11px] text-ink-400">
          {columns.map(([k, l]) => <th key={k} className="px-4 py-2 font-medium">{l}</th>)}<th />
        </tr></thead>
        <tbody className="divide-y divide-ink-950/15">
          {rows.map((r) => (
            <tr key={r.id}>
              {columns.map(([k, , render]) => <td key={k} className="px-4 py-2.5">{render ? render(r) : r[k]}</td>)}
              <td className="whitespace-nowrap px-4 py-2 text-right">
                <Button size="sm" variant="ghost" icon={Pencil} onClick={() => { setError(null); setForm(toForm(r)) }} />
                {onDelete && <Button size="sm" variant="ghost" icon={Trash2} title={deleteLabel} onClick={() => window.confirm(`${deleteLabel} ${r.name || r.email}?`) && onDelete(r)} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? `Edit` : `Add`}
        footer={<><Button variant="secondary" onClick={() => setForm(null)}>Cancel</Button><Button onClick={save} loading={busy}>Save</Button></>}>
        {form && fields(form, setForm)}
        <ErrorBox error={error} />
      </Modal>
    </Card>
  )
}

function SettingsTab() {
  const { data, error, reload } = useLoad(() => api.settings(), [])
  const integrations = useLoad(() => api.integrations(), [])
  const [values, setValues] = useState(null)
  const [testing, setTesting] = useState(null)
  const [testResult, setTestResult] = useState(null)
  const [checks, setChecks] = useState({})
  const checkTool = async (name) => {
    setChecks((c) => ({ ...c, [name]: 'busy' }))
    try { const r = await api.checkIntegration(name); setChecks((c) => ({ ...c, [name]: { ok: true, text: r.message, url: r.url } })) }
    catch (e) { setChecks((c) => ({ ...c, [name]: { ok: false, text: String(e.message || e) } })) }
  }
  const runTest = async (channel) => {
    setTesting(channel); setTestResult(null)
    try { const r = await api.testDelivery(channel); setTestResult({ ok: true, text: r.message }) }
    catch (e) { setTestResult({ ok: false, text: String(e.message || e) }) }
    finally { setTesting(null) }
  }
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const user = useUser()
  useEffect(() => { if (data) setValues(data.values) }, [data])
  if (error) return <ErrorBox error={error} />
  if (!data || !values) return <Spinner />
  const env = data.environment
  const admin = user.role === 'admin'
  const save = async () => {
    setSaveError(null)
    try { await api.saveSettings(values); setSaved(true); setTimeout(() => setSaved(false), 2000); reload() } catch (e) { setSaveError(e) }
  }
  const Check = ({ ok, label, hint }) => (
    <div className="flex items-start gap-2.5 py-1.5">
      {ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-ink-950" /> : <CircleDashed className="mt-0.5 h-4 w-4 text-ink-300" />}
      <div><p className="text-sm">{label}</p>{hint && <p className="text-xs text-ink-500">{hint}</p>}</div>
    </div>
  )
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        <Card>
          <CardHeader title="Bot and reports" subtitle={admin ? 'How the bot introduces itself and where reports go' : 'Only admins can change these'} />
          <div className="space-y-3 p-5">
            <Field label="Bot name"><Input disabled={!admin} value={values.bot_name} onChange={(e) => setValues({ ...values, bot_name: e.target.value })} /></Field>
            <Field label="Recording notice" hint="Posted once in the chat when the bot is admitted. {bot_name} and {organizer} are filled in. Leave empty to post nothing."><Textarea disabled={!admin} value={values.consent_notice} onChange={(e) => setValues({ ...values, consent_notice: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Default full-report audience"><Select disabled={!admin} value={values.default_share_full.audience} onChange={(e) => setValues({ ...values, default_share_full: { audience: e.target.value, user_ids: [] } })}>
                <option value="organizer">Only the organizer</option><option value="participants">All participants</option><option value="managers">Managers and team leads</option></Select></Field>
              <Field label="Default employee-update audience"><Select disabled={!admin} value={values.default_share_employee.audience} onChange={(e) => setValues({ ...values, default_share_employee: { audience: e.target.value, user_ids: [] } })}>
                <option value="organizer">Only the organizer</option><option value="participants">All participants</option><option value="managers">Managers and team leads</option></Select></Field>
            </div>
            <Field label="Create tasks automatically in" hint="New action items and commitments from each meeting are pushed to this tool.">
              <Select disabled={!admin} value={values.auto_push_provider || ''} onChange={(e) => setValues({ ...values, auto_push_provider: e.target.value || null })}>
                <option value="">Off - push items by hand</option>
                {(integrations.data || []).filter((p) => p.configured).map((p) => <option key={p.name} value={p.name}>{p.label}</option>)}
              </Select>
            </Field>
            <div className="grid gap-3 border-t-2 border-ink-950/10 pt-3 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs font-bold">Send the report after each meeting</p>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-ink-950" disabled={!admin || !env.email_configured}
                  checked={!!values.deliver_email} onChange={(e) => setValues({ ...values, deliver_email: e.target.checked })} />
                  By email to everyone it's shared with {!env.email_configured && <span className="text-xs text-ink-500">(set SMTP_* in .env)</span>}</label>
                <label className="mt-1 flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-ink-950" disabled={!admin || !env.slack_configured}
                  checked={!!values.deliver_slack} onChange={(e) => setValues({ ...values, deliver_slack: e.target.checked })} />
                  Summary to Slack {!env.slack_configured && <span className="text-xs text-ink-500">(set SLACK_WEBHOOK_URL)</span>}</label>
                <p className="mt-1 text-[11px] text-ink-500">Slack only gets reports shared with participants or managers.</p>
                {admin && (env.email_configured || env.slack_configured) && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {env.email_configured && <Button size="sm" variant="secondary" loading={testing === 'email'} onClick={() => runTest('email')}>Send test email</Button>}
                    {env.slack_configured && <Button size="sm" variant="secondary" loading={testing === 'slack'} onClick={() => runTest('slack')}>Send test to Slack</Button>}
                  </div>
                )}
                {testResult && <p className={`mt-1 text-xs font-medium ${testResult.ok ? 'text-ink-950' : 'text-signal-red'}`}>{testResult.text}</p>}
              </div>
              <Field label="Delete transcripts and recordings after (days)" hint="0 keeps them. Reports and progress records are always kept. Recordings are also deleted at MeetStream.">
                <Input type="number" min="0" disabled={!admin} value={values.transcript_retention_days ?? 0}
                  onChange={(e) => setValues({ ...values, transcript_retention_days: Math.max(0, parseInt(e.target.value || '0', 10)) })} />
              </Field>
            </div>
            <ErrorBox error={saveError} />
            {admin && <Button onClick={save}>{saved ? 'Saved' : 'Save settings'}</Button>}
          </div>
        </Card>
      </div>
      <div className="space-y-5">
        <Card>
          <CardHeader title="Server setup" subtitle="Set in .env, then restart the backend" />
          <div className="px-5 py-3">
            <Check ok={env.meetstream_configured} label="MeetStream API key" hint="Needed to send bots into meetings." />
            <Check ok={env.email_configured || env.slack_configured} label="Report delivery (optional)" hint="SMTP_* for email, SLACK_WEBHOOK_URL for Slack." />
            <Check ok={env.analysis_configured} label={env.analysis_provider === 'gemini' ? 'Gemini API key' : 'Anthropic API key'} hint={`Analyses transcripts with ${env.analysis_model}.`} />
            <Check ok={!!env.public_url} label="Public address (optional)"
              hint={env.public_url
                ? `${env.public_url}${env.tunnel?.state === 'up' ? ' (automatic tunnel)' : ''}`
                : env.tunnel?.state === 'starting' ? 'Starting the tunnel…'
                : env.tunnel?.error || 'Install cloudflared or set PUBLIC_URL: live webhooks, and the stand-up host leaves right after its goodbye.'} />
            <p className="mt-2 text-xs text-ink-500">Transcription: {env.transcript_provider} · Stand-up voice model: {env.mia_model} · Timezone: {env.timezone}</p>
          </div>
        </Card>
        <Card>
          <CardHeader title="Task tools" action={isManager(user) && <Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => api.syncIntegrations().then(() => integrations.reload())}>Sync now</Button>} />
          <div className="divide-y divide-ink-950/15">
            {(integrations.data || []).map((p) => (
              <div key={p.name} className="px-5 py-2.5">
                <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{p.label}</span>
                  <span className="flex items-center gap-1.5">
                    {p.configured && isManager(user) && <Button size="sm" variant="ghost" loading={checks[p.name] === 'busy'} onClick={() => checkTool(p.name)}>Check</Button>}
                    {p.configured ? <Badge tone="green">Set up</Badge> : <Badge>Not set up</Badge>}</span></div>
                {!p.configured && <p className="mt-0.5 font-mono text-[10px] text-ink-400">{p.required_env.join(' ')}</p>}
                {checks[p.name] && checks[p.name] !== 'busy' && <p className={`mt-0.5 text-xs font-medium ${checks[p.name].ok ? 'text-ink-950' : 'text-signal-red'}`}>{checks[p.name].text}{checks[p.name].url && <> <a href={checks[p.name].url} target="_blank" rel="noreferrer" className="font-bold underline decoration-2 underline-offset-2 hover:bg-accent-soft">Open board</a></>}</p>}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}

export default function Admin() {
  const user = useUser()
  const manager = isManager(user)
  const [tab, setTab] = useState(manager ? 'people' : 'settings')
  const employees = useLoad(() => api.employees(), [])
  const teams = useLoad(() => api.teams(), [])
  const projects = useLoad(() => api.projects(), [])
  const users = useLoad(() => api.users(), [])
  const empName = (id) => (employees.data || []).find((e) => e.id === id)?.name || '—'
  const teamOpts = (teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)
  const empOpts = (employees.data || []).filter((e) => e.active).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)
  const reloadAll = () => { employees.reload(); teams.reload(); projects.reload(); users.reload() }

  if (!manager) return <><PageHeader title="Settings" /><SettingsTab /></>
  if (!employees.data || !teams.data || !projects.data || !users.data) return <Spinner />

  return (
    <>
      <PageHeader title="Admin" subtitle="People, teams, projects, logins and how the bot behaves" />
      <div className="mb-5"><Tabs value={tab} onChange={setTab} tabs={[['people', 'Employees'], ['teams', 'Teams'], ['projects', 'Projects'], ...(user.role === 'admin' ? [['users', 'Users']] : []), ['settings', 'Bot & settings']]} /></div>

      {tab === 'people' && (
        <Crud title="Employees" rows={employees.data.filter((e) => e.active)}
          columns={[['name', 'Name'], ['title', 'Title'], ['team_name', 'Team'], ['aliases', 'Also appears as', (r) => r.aliases.join(', ') || '—']]}
          blank={() => ({ name: '', email: '', title: '', team_id: '', aliases: '', project_ids: [] })}
          toForm={(r) => ({ ...r, team_id: r.team_id || '', aliases: r.aliases.join(', ') })}
          fields={(f, set) => <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name"><Input value={f.name} onChange={(e) => set({ ...f, name: e.target.value })} /></Field>
              <Field label="Email"><Input value={f.email || ''} onChange={(e) => set({ ...f, email: e.target.value })} /></Field>
              <Field label="Title"><Input value={f.title} onChange={(e) => set({ ...f, title: e.target.value })} /></Field>
              <Field label="Team"><Select value={f.team_id} onChange={(e) => set({ ...f, team_id: e.target.value })}><option value="">—</option>{teamOpts}</Select></Field>
            </div>
            <Field label="Other names in meetings" hint="Comma separated - e.g. how Zoom shows them ('Sam O', 'samo-laptop'). Names you map on a meeting are added here automatically.">
              <Input value={f.aliases} onChange={(e) => set({ ...f, aliases: e.target.value })} /></Field>
            <Field label="Projects">
              <div className="flex flex-wrap gap-2">{projects.data.map((p) => (
                <label key={p.id} className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={(f.project_ids || []).includes(p.id)} className="h-4 w-4 rounded-sm border-2 border-ink-950 accent-ink-950"
                  onChange={(e) => set({ ...f, project_ids: e.target.checked ? [...(f.project_ids || []), p.id] : f.project_ids.filter((x) => x !== p.id) })} />{p.name}</label>
              ))}</div>
            </Field>
          </>}
          onSave={async (f) => {
            const body = { name: f.name, email: f.email || null, title: f.title, team_id: f.team_id || null, aliases: split(f.aliases), project_ids: f.project_ids || [], active: true }
            f.id ? await api.updateEmployee(f.id, body) : await api.createEmployee(body)
            reloadAll()
          }}
          onDelete={async (r) => { await api.deactivateEmployee(r.id); reloadAll() }} deleteLabel="Deactivate" />
      )}

      {tab === 'teams' && (
        <Crud title="Teams" rows={teams.data}
          columns={[['name', 'Team'], ['description', 'Description'], ['lead', 'Team lead', (r) => empName(r.lead_employee_id)]]}
          blank={() => ({ name: '', description: '', lead_employee_id: '' })}
          toForm={(r) => ({ ...r, lead_employee_id: r.lead_employee_id || '' })}
          fields={(f, set) => <>
            <Field label="Name"><Input value={f.name} onChange={(e) => set({ ...f, name: e.target.value })} /></Field>
            <Field label="Description"><Input value={f.description} onChange={(e) => set({ ...f, description: e.target.value })} /></Field>
            <Field label="Team lead" hint="Team leads can see their team's records and reports shared with managers and leads.">
              <Select value={f.lead_employee_id} onChange={(e) => set({ ...f, lead_employee_id: e.target.value })}><option value="">—</option>{empOpts}</Select></Field>
          </>}
          onSave={async (f) => {
            const body = { name: f.name, description: f.description, lead_employee_id: f.lead_employee_id || null }
            f.id ? await api.updateTeam(f.id, body) : await api.createTeam(body)
            reloadAll()
          }}
          onDelete={async (r) => { await api.deleteTeam(r.id); reloadAll() }} />
      )}

      {tab === 'projects' && (
        <Crud title="Projects" rows={projects.data}
          columns={[['name', 'Project'], ['status', 'Status'], ['keywords', 'Keywords', (r) => r.keywords.join(', ') || '—'], ['members', 'People', (r) => r.member_ids.length]]}
          blank={() => ({ name: '', description: '', team_id: '', status: 'active', keywords: '', member_ids: [] })}
          toForm={(r) => ({ ...r, team_id: r.team_id || '', keywords: r.keywords.join(', ') })}
          fields={(f, set) => <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name"><Input value={f.name} onChange={(e) => set({ ...f, name: e.target.value })} /></Field>
              <Field label="Status"><Select value={f.status} onChange={(e) => set({ ...f, status: e.target.value })}><option value="active">Active</option><option value="paused">Paused</option><option value="done">Done</option></Select></Field>
            </div>
            <Field label="Description"><Input value={f.description} onChange={(e) => set({ ...f, description: e.target.value })} /></Field>
            <Field label="Team"><Select value={f.team_id} onChange={(e) => set({ ...f, team_id: e.target.value })}><option value="">—</option>{teamOpts}</Select></Field>
            <Field label="Keywords" hint="Words that identify this project in conversation, comma separated."><Input value={f.keywords} onChange={(e) => set({ ...f, keywords: e.target.value })} /></Field>
          </>}
          onSave={async (f) => {
            const body = { name: f.name, description: f.description, team_id: f.team_id || null, status: f.status, keywords: split(f.keywords), member_ids: f.member_ids }
            f.id ? await api.updateProject(f.id, body) : await api.createProject(body)
            reloadAll()
          }}
          onDelete={async (r) => { await api.deleteProject(r.id); reloadAll() }} />
      )}

      {tab === 'users' && (
        <Crud title="Users (logins)" rows={users.data}
          columns={[['name', 'Name'], ['email', 'Email'], ['role', 'Role', (r) => <Badge tone={r.role === 'admin' ? 'red' : r.role === 'manager' ? 'blue' : 'gray'}>{r.role}</Badge>], ['employee', 'Employee profile', (r) => empName(r.employee_id)]]}
          blank={() => ({ name: '', email: '', role: 'employee', password: '', employee_id: '' })}
          toForm={(r) => ({ ...r, password: '', employee_id: r.employee_id || '' })}
          fields={(f, set) => <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Name"><Input value={f.name} onChange={(e) => set({ ...f, name: e.target.value })} /></Field>
              <Field label="Email"><Input value={f.email} onChange={(e) => set({ ...f, email: e.target.value })} /></Field>
              <Field label="Role"><Select value={f.role} onChange={(e) => set({ ...f, role: e.target.value })}><option value="employee">Employee</option><option value="manager">Manager</option><option value="admin">Admin</option></Select></Field>
              <Field label={f.id ? 'New password (optional)' : 'Password'}><Input type="password" value={f.password} onChange={(e) => set({ ...f, password: e.target.value })} /></Field>
            </div>
            <Field label="Linked employee profile" hint="Links this login to the person's meeting records."><Select value={f.employee_id} onChange={(e) => set({ ...f, employee_id: e.target.value })}><option value="">—</option>{empOpts}</Select></Field>
          </>}
          onSave={async (f) => {
            const body = { name: f.name, email: f.email, role: f.role, password: f.password || null, employee_id: f.employee_id || null }
            f.id ? await api.updateUser(f.id, body) : await api.createUser(body)
            reloadAll()
          }}
          onDelete={async (r) => { await api.deleteUser(r.id); reloadAll() }} />
      )}

      {tab === 'settings' && <SettingsTab />}
    </>
  )
}
