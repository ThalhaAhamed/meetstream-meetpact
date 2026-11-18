import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, AudioLines, Bot, CalendarDays, Check, KanbanSquare, Mail, PartyPopper, Sparkles, Users } from 'lucide-react'
import { api } from '../api'
import CalendarPanel from '../components/CalendarPanel'
import TeamBoardSettings from '../components/TeamBoardSettings'
import TrelloConnect from '../components/TrelloConnect'
import VoicePicker from '../components/VoicePicker'
import { Badge, Button, Card, ErrorBox, Field, Input, PageHeader, Spinner, Textarea, cx, useLoad } from '../components/ui'

const STEPS = [
  ['meetstream', 'Meeting bot', Bot],
  ['ai', 'AI notes', Sparkles],
  ['voice', 'Stand-up voice', AudioLines],
  ['team', 'Your team', Users],
  ['board', 'Task board', KanbanSquare],
  ['calendar', 'Calendar', CalendarDays],
  ['reports', 'Reports', Mail],
  ['done', 'Done', PartyPopper],
]
const link = 'font-bold underline decoration-2 underline-offset-2 hover:bg-accent-soft'
const AI = [
  ['gemini', 'Gemini', 'Google · key from aistudio.google.com'],
  ['anthropic', 'Claude', 'Anthropic · key from console.anthropic.com'],
  ['openai', 'OpenAI', 'Key from platform.openai.com'],
  ['xai', 'Grok', 'xAI · key from console.x.ai'],
]
const AI_NAME = { gemini: 'Gemini', anthropic: 'Claude', openai: 'OpenAI', xai: 'Grok' }
const AI_KEY = { gemini: 'GEMINI_API_KEY', anthropic: 'ANTHROPIC_API_KEY', openai: 'OPENAI_API_KEY', xai: 'XAI_API_KEY' }
const AI_MODEL = { gemini: 'GEMINI_MODEL', anthropic: 'ANALYSIS_MODEL', openai: 'OPENAI_MODEL', xai: 'XAI_MODEL' }

function KeyField({ label, field, keys, value, onChange, placeholder, secret = true, hint }) {
  const k = keys?.[field] || {}
  if (k.from_env) return <Field label={label}><p className="text-sm"><Badge tone="green">Set in .env</Badge></p></Field>
  return (
    <Field label={label} hint={hint || (k.set && secret ? 'Saved. Type a new value to replace it.' : undefined)}>
      <Input type={secret ? 'password' : 'text'} value={value ?? ''} onChange={(e) => onChange(e.target.value)}
        placeholder={k.set && secret ? '••••••••  (saved)' : placeholder} autoComplete="off" />
    </Field>
  )
}

function Result({ result }) {
  if (!result) return null
  return result.ok
    ? <p className="flex items-center gap-1.5 text-sm font-medium"><Check className="h-4 w-4" />{result.text}</p>
    : <ErrorBox error={result.text} />
}

// First-run guide: everything a new install needs, one step at a time.
export default function Setup() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const status = useLoad(() => api.setupStatus(), [])
  const [step, setStep] = useState(params.get('calendar') || params.get('calendar_error') ? 'calendar' : 'meetstream')
  const [form, setForm] = useState({})
  const [busy, setBusy] = useState(null)
  const [result, setResult] = useState(null)
  const s = status.data
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }))
  const index = STEPS.findIndex(([k]) => k === step)
  const provider = form.ANALYSIS_PROVIDER || s?.analysis_provider || 'gemini'
  const go = (k) => { setStep(k); setResult(null) }

  const saveAndCheck = async (fields, check) => {
    setBusy('save'); setResult(null)
    try {
      const values = Object.fromEntries(fields.filter((f) => form[f] !== undefined && form[f] !== '').map((f) => [f, form[f]]))
      if (Object.keys(values).length) await api.saveSetupKeys(values)
      const r = check ? await api.checkSetup(check) : { message: 'Saved.' }
      setResult({ ok: true, text: r.message }); setForm({}); status.reload()
    } catch (e) { setResult({ ok: false, text: String(e.message || e) }) } finally { setBusy(null) }
  }

  if (!s) return <Spinner />
  const doneFor = {
    meetstream: s.meetstream, ai: s.analysis, voice: s.voice_chosen, team: s.teams.length > 0 && s.people > 1,
    board: s.teams.length > 0, calendar: s.calendar, reports: s.email || s.slack, done: s.done,
  }

  return (
    <>
      <PageHeader title="Set up MeetPact" subtitle="A few minutes, one step at a time. You can come back here from Admin." />
      <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav className="flex gap-2 overflow-x-auto lg:flex-col" aria-label="Setup steps">
          {STEPS.map(([k, label, Icon], i) => (
            <button key={k} onClick={() => go(k)}
              className={cx('flex shrink-0 items-center gap-2.5 rounded-md border-2 px-3 py-2 text-left text-sm font-bold',
                step === k ? 'border-ink-950 bg-accent shadow-press' : 'border-transparent hover:border-ink-950 hover:bg-white')}>
              <span className={cx('flex h-5 w-5 items-center justify-center rounded border-2 border-ink-950 text-[10px]', doneFor[k] ? 'bg-pop-mint' : 'bg-white')}>
                {doneFor[k] ? <Check className="h-3 w-3" /> : i + 1}</span>
              <Icon className="h-4 w-4" />{label}
            </button>
          ))}
        </nav>

        <Card className="p-5">
          {step === 'meetstream' && <div className="max-w-xl space-y-4">
            <h2 className="text-lg font-bold">Connect the meeting bot</h2>
            <p className="text-sm text-ink-700">MeetPact sends a <a className={link} href="https://meetstream.ai" target="_blank" rel="noreferrer">MeetStream</a> bot
              into Google Meet, Zoom and Teams. Create an API key at <a className={link} href="https://app.meetstream.ai" target="_blank" rel="noreferrer">app.meetstream.ai</a>.</p>
            <KeyField label="MeetStream API key" field="MEETSTREAM_API_KEY" keys={s.keys} value={form.MEETSTREAM_API_KEY} onChange={set('MEETSTREAM_API_KEY')} />
            <Button loading={busy === 'save'} onClick={() => saveAndCheck(['MEETSTREAM_API_KEY'], 'meetstream')}>Save and check</Button>
            <Result result={result} />
          </div>}

          {step === 'ai' && <div className="max-w-xl space-y-4">
            <h2 className="text-lg font-bold">Pick the AI that writes the notes</h2>
            <p className="text-sm text-ink-700">It reads each transcript and writes the summary, decisions, action items and everyone's progress.</p>
            <div className="grid grid-cols-2 gap-2">
              {AI.map(([k, label, hint]) => (
                <button key={k} type="button" onClick={() => set('ANALYSIS_PROVIDER')(k)}
                  className={cx('rounded-md border-2 p-3 text-left text-sm', provider === k ? 'border-ink-950 bg-accent shadow-press' : 'border-ink-300 bg-white')}>
                  <span className="block font-bold">{label}</span><span className="text-xs text-ink-600">{hint}</span>
                </button>
              ))}
            </div>
            <KeyField label={`${AI_NAME[provider]} API key`} field={AI_KEY[provider]} keys={s.keys} value={form[AI_KEY[provider]]} onChange={set(AI_KEY[provider])} />
            <KeyField label="Model" field={AI_MODEL[provider]} secret={false} keys={s.keys} value={form[AI_MODEL[provider]]} onChange={set(AI_MODEL[provider])}
              placeholder={s.keys?.[AI_MODEL[provider]]?.value || ''} hint="Leave as is unless your key can't use this model." />
            <Button loading={busy === 'save'} onClick={() => saveAndCheck(['ANALYSIS_PROVIDER', AI_KEY[provider], AI_MODEL[provider]], 'analysis')}>Save and check</Button>
            <Result result={result} />
          </div>}

          {step === 'voice' && <div className="max-w-2xl space-y-4">
            <h2 className="text-lg font-bold">Choose the stand-up host's voice</h2>
            <p className="text-sm text-ink-700">In stand-up mode MeetPact speaks in the meeting: it introduces itself, asks each person for their update and wraps up.
              Notes and summaries use the AI from the previous step either way.</p>
            <VoicePicker />
          </div>}

          {step === 'team' && <TeamStep teams={s.teams} onSaved={status.reload} />}

          {step === 'board' && <div className="space-y-4">
            <h2 className="text-lg font-bold">Where does each team keep its tasks?</h2>
            <p className="text-sm text-ink-700">Use MeetPact's own board, or a team's existing Trello board: MeetPact shows it, knows who is on each card,
              adds new tasks from meetings and moves cards when people report progress.</p>
            <div className="max-w-xl rounded-md border-2 border-ink-950 p-3"><p className="mb-2 text-xs font-bold">Trello (only needed for Trello boards)</p>
              <TrelloConnect onChange={status.reload} /></div>
            {s.teams.length ? s.teams.map((t) => (
              <div key={t.id} className="max-w-xl"><p className="mb-1 text-sm font-bold">{t.name}</p><TeamBoardSettings team={t} onSaved={status.reload} /></div>
            )) : <p className="text-sm text-ink-600">Add a team in the previous step first.</p>}
          </div>}

          {step === 'calendar' && <div className="space-y-4">
            <h2 className="text-lg font-bold">Join meetings from the calendar <span className="text-sm font-medium text-ink-500">(optional)</span></h2>
            {!s.google_sign_in && <div className="max-w-xl space-y-3">
              <p className="text-sm text-ink-700">For one-click Google sign-in, create an OAuth client (Web application) in Google Cloud with the
                redirect URI <code className="font-mono text-xs">{s.app_url.includes('localhost') ? 'http://localhost:8000' : s.app_url.replace(/\/$/, '')}/api/calendar/google/callback</code>.
                Steps: docs/integrations.md.</p>
              <KeyField label="Google OAuth client ID" field="GOOGLE_CLIENT_ID" secret={false} keys={s.keys} value={form.GOOGLE_CLIENT_ID} onChange={set('GOOGLE_CLIENT_ID')} placeholder="….apps.googleusercontent.com" />
              <KeyField label="Google OAuth client secret" field="GOOGLE_CLIENT_SECRET" keys={s.keys} value={form.GOOGLE_CLIENT_SECRET} onChange={set('GOOGLE_CLIENT_SECRET')} placeholder="GOCSPX-…" />
              <Button loading={busy === 'save'} onClick={() => saveAndCheck(['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'])}>Save</Button>
              <Result result={result} />
            </div>}
            <CalendarPanel returnTo="/setup" className="" />
          </div>}

          {step === 'reports' && <ReportsStep s={s} form={form} set={set} busy={busy} saveAndCheck={saveAndCheck} result={result} />}

          {step === 'done' && <div className="max-w-xl space-y-4">
            <h2 className="text-lg font-bold">You're set</h2>
            <ul className="space-y-1.5 text-sm">
              {STEPS.slice(0, -1).map(([k, label]) => (
                <li key={k} className="flex items-center gap-2">
                  {doneFor[k] ? <Badge tone="green">Done</Badge> : <Badge>{['calendar', 'reports'].includes(k) ? 'Optional' : 'To do'}</Badge>}{label}</li>
              ))}
            </ul>
            <p className="text-sm text-ink-700">Next: open <b>Meetings → Send bot to a meeting</b>, or schedule a recurring stand-up under <b>Schedules</b>.</p>
            <Button onClick={async () => { await api.finishSetup(); navigate('/meetings') }}>Finish and send a bot</Button>
          </div>}

          <div className="mt-6 flex items-center justify-between border-t-2 border-ink-950/10 pt-4">
            <Button variant="ghost" icon={ArrowLeft} disabled={index === 0} onClick={() => go(STEPS[index - 1][0])}>Back</Button>
            {index < STEPS.length - 1 && <Button variant="secondary" onClick={() => go(STEPS[index + 1][0])}>
              {doneFor[step] ? 'Next' : 'Skip for now'} <ArrowRight className="h-4 w-4" /></Button>}
          </div>
        </Card>
      </div>
    </>
  )
}

function TeamStep({ teams, onSaved }) {
  const [name, setName] = useState(teams[0]?.name ? '' : 'My team')
  const [people, setPeople] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const save = async () => {
    setBusy(true); setResult(null)
    try {
      const team = await api.createTeam({ name: name.trim(), description: '' })
      const rows = people.split('\n').map((l) => l.split(',').map((x) => x.trim())).filter(([n]) => n)
      for (const [n, email] of rows) await api.createEmployee({ name: n, email: email || null, team_id: team.id, aliases: [], title: '' })
      setResult({ ok: true, text: `Created "${team.name}" with ${rows.length} ${rows.length === 1 ? 'person' : 'people'}.` })
      setName(''); setPeople(''); onSaved()
    } catch (e) { setResult({ ok: false, text: String(e.message || e) }) } finally { setBusy(false) }
  }
  return (
    <div className="max-w-xl space-y-4">
      <h2 className="text-lg font-bold">Who's on the team?</h2>
      <p className="text-sm text-ink-700">MeetPact matches the names people use in meetings to these people, and tracks each person's work.</p>
      {teams.length > 0 && <p className="text-sm">Teams so far: {teams.map((t) => <Badge key={t.id} className="mr-1">{t.name}</Badge>)}</p>}
      <Field label="Team name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Engineering" /></Field>
      <Field label="People" hint="One per line: name, email (email optional). Add logins later under Admin → Users.">
        <Textarea value={people} onChange={(e) => setPeople(e.target.value)} placeholder={'Priya Raman, priya@company.com\nSam Okafor'} className="min-h-[120px]" />
      </Field>
      <Button loading={busy} disabled={!name.trim()} onClick={save}>Add team</Button>
      <Result result={result} />
    </div>
  )
}

function ReportsStep({ s, form, set, busy, saveAndCheck, result }) {
  const [test, setTest] = useState(null)
  const run = async (channel) => {
    setTest({ busy: channel })
    try { const r = await api.testDelivery(channel); setTest({ ok: true, text: r.message }) } catch (e) { setTest({ ok: false, text: String(e.message || e) }) }
  }
  return (
    <div className="max-w-xl space-y-4">
      <h2 className="text-lg font-bold">Send reports after each meeting <span className="text-sm font-medium text-ink-500">(optional)</span></h2>
      <KeyField label="Slack incoming webhook" field="SLACK_WEBHOOK_URL" keys={s.keys} value={form.SLACK_WEBHOOK_URL} onChange={set('SLACK_WEBHOOK_URL')}
        placeholder="https://hooks.slack.com/services/…" hint="api.slack.com/apps → your app → Incoming Webhooks → Add New Webhook." />
      <div className="grid gap-3 sm:grid-cols-2">
        <KeyField label="SMTP server" field="SMTP_HOST" secret={false} keys={s.keys} value={form.SMTP_HOST} onChange={set('SMTP_HOST')} placeholder="smtp.gmail.com" />
        <KeyField label="Port" field="SMTP_PORT" secret={false} keys={s.keys} value={form.SMTP_PORT} onChange={set('SMTP_PORT')} placeholder="587" />
        <KeyField label="Username" field="SMTP_USER" secret={false} keys={s.keys} value={form.SMTP_USER} onChange={set('SMTP_USER')} placeholder="you@company.com" />
        <KeyField label="Password" field="SMTP_PASSWORD" keys={s.keys} value={form.SMTP_PASSWORD} onChange={set('SMTP_PASSWORD')} hint="Gmail: an app password, not your normal one." />
        <KeyField label="From" field="SMTP_FROM" secret={false} keys={s.keys} value={form.SMTP_FROM} onChange={set('SMTP_FROM')} placeholder="MeetPact <you@company.com>" />
      </div>
      <Button loading={busy === 'save'} onClick={async () => {
        const slack = !!form.SLACK_WEBHOOK_URL, email = !!(form.SMTP_HOST || form.SMTP_FROM)
        await saveAndCheck(['SLACK_WEBHOOK_URL', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD', 'SMTP_FROM'])
        if (slack || email) await api.saveSettings({ ...(slack && { deliver_slack: true }), ...(email && { deliver_email: true }) }).catch(() => {})
      }}>Save</Button>
      <Result result={result} />
      {(s.email || s.slack) && <div className="flex flex-wrap gap-2">
        {s.email && <Button size="sm" variant="secondary" loading={test?.busy === 'email'} onClick={() => run('email')}>Send test email</Button>}
        {s.slack && <Button size="sm" variant="secondary" loading={test?.busy === 'slack'} onClick={() => run('slack')}>Send test to Slack</Button>}
      </div>}
      {test && !test.busy && <Result result={test} />}
      <p className="text-xs text-ink-500">Turn delivery on or off any time under Admin → Bot & settings.</p>
    </div>
  )
}
