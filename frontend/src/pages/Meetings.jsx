import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bot, FileUp, Video } from 'lucide-react'
import { api } from '../api'
import ShareFields from '../components/ShareFields'
import {
  BotStatus, Button, Card, Empty, ErrorBox, Field, Input, Modal, PageHeader, ProcStatus, Select, Spinner, Tabs, Textarea,
  fmtDateTime, useLoad,
} from '../components/ui'

const LIVE = ['scheduled', 'joining', 'waiting_room', 'in_meeting', 'recording', 'paused']

function MeetingFormBits({ form, setForm, teams, projects }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Team"><Select value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value })}>
          <option value="">—</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
        <Field label="Project"><Select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
          <option value="">—</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
      </div>
      <ShareFields full={form.share_full} employee={form.share_employee}
        onChange={({ full, employee }) => setForm({ ...form, share_full: full, share_employee: employee })} />
    </>
  )
}

const blank = () => ({
  title: '', meeting_link: '', mode: 'notetaker', team_id: '', project_id: '', join_at: '',
  share_full: { audience: 'participants', user_ids: [] }, share_employee: { audience: 'managers', user_ids: [] },
})

export default function Meetings() {
  const [tab, setTab] = useState('all')
  const { data, error, loading, reload } = useLoad(() => api.meetings(), [])
  const teams = useLoad(() => api.teams(), [])
  const projects = useLoad(() => api.projects(), [])
  const settings = useLoad(() => api.settings(), [])
  const [send, setSend] = useState(null)
  const [imp, setImp] = useState(null)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState(null)
  const nav = useNavigate()
  const env = settings.data?.environment

  const rows = (data || []).filter((m) =>
    tab === 'all' ? true : tab === 'live' ? LIVE.includes(m.bot_status) : tab === 'ready' ? m.processing_status === 'done'
      : m.processing_status === 'failed' || ['failed', 'denied', 'not_admitted'].includes(m.bot_status))

  const clean = (f) => ({ ...f, team_id: f.team_id || null, project_id: f.project_id || null })
  const submitSend = async () => {
    setBusy(true); setFormError(null)
    try {
      const m = await api.createMeeting({ ...clean(send), join_at: send.join_at ? new Date(send.join_at).toISOString() : null })
      setSend(null); nav(`/meetings/${m.id}`)
    } catch (e) { setFormError(e) } finally { setBusy(false) }
  }
  const submitImport = async () => {
    setBusy(true); setFormError(null)
    try {
      const m = await api.importTranscript({ ...clean(imp), meeting_date: imp.meeting_date || null })
      setImp(null); nav(`/meetings/${m.id}`)
    } catch (e) { setFormError(e) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Meetings" subtitle="Every meeting the notetaker attended, with its report"
        actions={<>
          <Button variant="secondary" icon={FileUp} onClick={() => { setFormError(null); setImp({ ...blank(), transcript: '', meeting_date: '' }) }}>Import transcript</Button>
          <Button icon={Bot} onClick={() => { setFormError(null); setSend(blank()) }}>Send bot to a meeting</Button>
        </>} />
      <ErrorBox error={error} />
      <Card>
        <div className="px-4 pt-2">
          <Tabs value={tab} onChange={setTab} tabs={[['all', 'All'], ['live', 'Live & upcoming'], ['ready', 'Reports ready'], ['problems', 'Problems']]} />
        </div>
        {loading && !data ? <Spinner /> : !rows.length ? <Empty icon={Video} title="No meetings here">Send the bot to a meeting link, set up a schedule, or import a transcript.</Empty> : (
          <div className="divide-y divide-ink-950/15">
            {rows.map((m) => (
              <Link key={m.id} to={`/meetings/${m.id}`} className="flex items-center gap-4 px-5 py-3 hover:bg-ink-50/60">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-medium">{m.title}</span>
                    {m.mode === 'standup' && <span className="text-[11px] text-ink-500">· AI-led stand-up</span>}
                  </div>
                  <p className="mt-0.5 line-clamp-1 text-xs text-ink-500">{m.overview || m.stop_reason || m.processing_error || `${m.participant_count} participants`}</p>
                </div>
                <span className="hidden w-36 text-right text-xs text-ink-500 sm:block">{fmtDateTime(m.scheduled_at || m.created_at)}</span>
                <div className="flex w-44 justify-end gap-1">
                  {LIVE.includes(m.bot_status) || m.processing_status === 'skipped' ? <BotStatus status={m.bot_status} /> : <ProcStatus status={m.processing_status} />}
                </div>
              </Link>
            ))}
          </div>
        )}
      </Card>

      <Modal open={!!send} onClose={() => setSend(null)} title="Send the notetaker to a meeting" wide
        footer={<><Button variant="secondary" onClick={() => setSend(null)}>Cancel</Button><Button onClick={submitSend} loading={busy} disabled={!send?.title || !send?.meeting_link}>{send?.join_at ? 'Schedule bot' : 'Send bot now'}</Button></>}>
        {send && <>
          {env && !env.meetstream_configured && <ErrorBox error="MEETSTREAM_API_KEY is not set on the server, so no bot can be sent. Add it to .env and restart." />}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Title"><Input autoFocus value={send.title} onChange={(e) => setSend({ ...send, title: e.target.value })} placeholder="Billing sync" /></Field>
            <Field label="Join at" hint="Leave empty to join now."><Input type="datetime-local" value={send.join_at} onChange={(e) => setSend({ ...send, join_at: e.target.value })} /></Field>
          </div>
          <Field label="Meeting link" hint="Zoom, Google Meet or Microsoft Teams."><Input value={send.meeting_link} onChange={(e) => setSend({ ...send, meeting_link: e.target.value })} placeholder="https://meet.google.com/abc-defg-hij" /></Field>
          <Field label="Mode">
            <Select value={send.mode} onChange={(e) => setSend({ ...send, mode: e.target.value })}>
              <option value="notetaker">Notetaker - listens, then writes the report</option>
              <option value="standup">AI stand-up - the bot runs the stand-up by voice, person by person</option>
            </Select>
          </Field>
          <MeetingFormBits form={send} setForm={setSend} teams={teams.data || []} projects={projects.data || []} />
          <p className="rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-600">When admitted, the bot introduces itself as an AI notetaker in the chat, says the meeting is recorded and transcribed, and explains how to opt out. People who join later get the same notice.</p>
          <ErrorBox error={formError} />
        </>}
      </Modal>

      <Modal open={!!imp} onClose={() => setImp(null)} title="Import a transcript" wide
        footer={<><Button variant="secondary" onClick={() => setImp(null)}>Cancel</Button><Button onClick={submitImport} loading={busy} disabled={!imp?.title || !imp?.transcript}>Analyse</Button></>}>
        {imp && <>
          <p className="text-xs text-ink-500">For meetings recorded elsewhere, or to try the analysis without a bot. One line per turn: <code>Name: what they said</code>.</p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Title"><Input autoFocus value={imp.title} onChange={(e) => setImp({ ...imp, title: e.target.value })} /></Field>
            <Field label="Meeting date"><Input type="date" value={imp.meeting_date} onChange={(e) => setImp({ ...imp, meeting_date: e.target.value })} /></Field>
          </div>
          <Field label="Transcript"><Textarea className="min-h-[180px] font-mono text-xs" value={imp.transcript} onChange={(e) => setImp({ ...imp, transcript: e.target.value })}
            placeholder={'Maya Chen: Hi all, quick round.\nPriya Raman: Yesterday I finished the export API. Today I will add rate limiting, should be done by Thursday.\nSam Okafor: Still on the invoice page, blocked on the API response shape.'} /></Field>
          <MeetingFormBits form={imp} setForm={setImp} teams={teams.data || []} projects={projects.data || []} />
          {env && !env.analysis_configured && <p className="text-xs text-amber-700">No AI key is set on the server (ANTHROPIC_API_KEY or GEMINI_API_KEY), so the analysis will fail until one is.</p>}
          <ErrorBox error={formError} />
        </>}
      </Modal>
    </>
  )
}
