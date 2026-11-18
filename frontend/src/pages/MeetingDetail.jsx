import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  CheckSquare, Download, ExternalLink, FileX2, Send, Gavel, HelpCircle, ListChecks, Pause, Play, RefreshCw, Trash2, UserX,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'
import { useUser } from '../user'
import ShareFields from '../components/ShareFields'
import UpdateCard from '../components/UpdateCard'
import {
  Badge, BotStatus, Button, Card, CardHeader, Empty, ErrorBox, List, PageHeader, ProcStatus, Select, Spinner, Tabs,
  fmtDateTime, useLoad,
} from '../components/ui'

const LIVE = ['scheduled', 'joining', 'waiting_room', 'in_meeting', 'recording', 'paused']
const ACTIVITY_LABEL = {
  notice_sent: 'Recording notice posted', paused: 'Recording paused', resumed: 'Recording resumed',
  removed: 'Bot removed', denied: 'Host denied the bot', data_deleted: 'Recording deleted',
}

function mmss(s) {
  if (s === null || s === undefined) return ''
  const n = Math.floor(s)
  return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`
}

export default function MeetingDetail() {
  const { id } = useParams()
  const user = useUser()
  const nav = useNavigate()
  const { data: m, error, loading, reload } = useLoad(() => api.meeting(id), [id])
  const directory = useLoad(() => api.directory(), [])
  const [tab, setTab] = useState(null)
  const [busy, setBusy] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [share, setShare] = useState(null)

  // Keep live and processing meetings fresh.
  useEffect(() => {
    if (!m) return
    const active = LIVE.includes(m.bot_status) || ['waiting', 'fetching', 'analysing'].includes(m.processing_status)
    if (!active) return
    const t = setInterval(reload, 5000)
    return () => clearInterval(t)
  }, [m, reload])

  useEffect(() => { if (m && !share) setShare({ full: m.share_full, employee: m.share_employee }) }, [m, share])

  if (error) return <ErrorBox error={error} />
  if (loading && !m) return <Spinner />
  const perms = m.permissions
  const current = tab || (perms.full ? 'report' : 'updates')

  const act = async (name, fn) => {
    setBusy(name); setActionError(null)
    try { await fn(); await reload() } catch (e) { setActionError(e) } finally { setBusy(null) }
  }
  const s = m.summary || {}
  const humans = m.participants.filter((p) => !p.is_bot)

  const tabs = [
    perms.full && ['report', 'Report'],
    ['updates', 'Employee updates', m.updates.length],
    perms.full && ['transcript', 'Transcript'],
    ['participants', 'Participants', humans.length],
    perms.full && ['activity', 'Activity', m.consent_events?.length],
    perms.share && ['sharing', 'Sharing'],
  ].filter(Boolean)

  return (
    <>
      <PageHeader
        title={<span className="flex flex-wrap items-center gap-2">{m.title}</span>}
        subtitle={<span className="flex flex-wrap items-center gap-2">
          {fmtDateTime(m.started_at || m.scheduled_at || m.created_at)}
          <span>·</span>{m.mode === 'standup' ? 'AI-led stand-up' : 'Notetaker'}
          <BotStatus status={m.bot_status} /><ProcStatus status={m.processing_status} />
          {m.meeting_link && <a href={m.meeting_link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-bold text-ink-950 underline decoration-2 underline-offset-2 hover:bg-accent-soft">Meeting link <ExternalLink className="h-3 w-3" /></a>}
        </span>}
        actions={<>
          {perms.manage && ['in_meeting', 'recording'].includes(m.bot_status) && <Button variant="secondary" icon={Pause} loading={busy === 'pause'} onClick={() => act('pause', () => api.pauseMeeting(id))}>Pause recording</Button>}
          {perms.manage && m.recording_paused && LIVE.includes(m.bot_status) && <Button variant="secondary" icon={Play} loading={busy === 'resume'} onClick={() => act('resume', () => api.resumeMeeting(id))}>Resume</Button>}
          {perms.manage && m.bot_id && LIVE.includes(m.bot_status) && <Button variant="danger" icon={UserX} loading={busy === 'remove'} onClick={() => act('remove', () => api.removeBot(id))}>{m.bot_status === 'scheduled' ? 'Cancel bot' : 'Remove bot'}</Button>}
          {perms.manage && ['done', 'failed'].includes(m.processing_status) && <Button variant="secondary" icon={RefreshCw} loading={busy === 're'} onClick={() => act('re', () => api.reprocess(id))}>Re-analyse</Button>}
          {perms.full && m.processing_status === 'done' && <a href={api.reportUrl(id)} download={`${m.title}.md`}><Button variant="secondary" icon={Download}>Report</Button></a>}
          {perms.share && m.processing_status === 'done' && <Button variant="secondary" icon={Send} loading={busy === 'send'} onClick={() => act('send', async () => { const r = await api.deliverReport(id); window.alert(`Sent ${r.emails} email(s)${r.slack ? ' and posted to Slack' : ''}.`) })}>Send report</Button>}
          {perms.share && m.bot_id && !m.media_deleted_at && !LIVE.includes(m.bot_status) &&
            <Button variant="ghost" icon={FileX2} loading={busy === 'media'} title="Delete transcript and recording" onClick={() => window.confirm('Delete the transcript here and the recording at MeetStream? The report and progress records are kept. This cannot be undone.') && act('media', () => api.deleteRecording(id))}>Delete recording</Button>}
          {(user.role === 'admin' || m.organizer_user_id === user.id) && !LIVE.includes(m.bot_status) &&
            <Button variant="ghost" icon={Trash2} onClick={() => window.confirm('Delete this meeting, its report, and its recording at MeetStream? Work-item history is kept. This cannot be undone.') && act('del', async () => { await api.deleteMeeting(id); nav('/meetings') })} />}
        </>}
      />
      <div className="space-y-3">
        <ErrorBox error={actionError} />
        {m.processing_status === 'failed' && <ErrorBox error={m.processing_error} />}
        {m.stop_reason && ['not_admitted', 'denied', 'failed'].includes(m.bot_status) && <ErrorBox error={m.stop_reason} />}
        {m.bot_status === 'waiting_room' && <p className="rounded-md border-2 border-ink-950 bg-pop-yellow/50 px-3 py-2 text-sm font-medium text-ink-950">The bot is in the waiting room. The host needs to admit it.</p>}
        {m.recording_paused && LIVE.includes(m.bot_status) && <p className="rounded-md border-2 border-ink-950 bg-pop-yellow/50 px-3 py-2 text-sm font-medium text-ink-950">Recording is paused. Nothing is captured until it is resumed.</p>}
        {!perms.full && <p className="rounded-lg bg-ink-100 px-3 py-2 text-sm text-ink-700">The organizer has not shared the full report with you. You can see the employee updates you have access to, including your own.</p>}
      </div>

      <Card className="mt-4">
        <div className="px-4 pt-2"><Tabs value={current} onChange={setTab} tabs={tabs} /></div>

        {current === 'report' && (m.processing_status !== 'done' ? (
          <Empty icon={ListChecks} title={LIVE.includes(m.bot_status) ? 'The meeting is still going' : 'The report is not ready yet'}>
            {LIVE.includes(m.bot_status) ? 'The report is written after the meeting ends and MeetStream finishes the transcript.' : 'This page refreshes on its own.'}
          </Empty>
        ) : (
          <div className="grid gap-6 p-5 lg:grid-cols-3">
            <div className="space-y-5 lg:col-span-2">
              <section><h3 className="mb-1.5 text-xs font-semibold text-ink-400">Summary</h3><p className="text-sm leading-relaxed text-ink-800">{s.overview}</p></section>
              <section><h3 className="mb-1.5 text-xs font-semibold text-ink-400">Key discussion points</h3><List items={s.key_points} /></section>
              <section><h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-ink-400"><Gavel className="h-3.5 w-3.5" />Decisions</h3><List items={s.decisions} empty="No decisions recorded" /></section>
              <section><h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-ink-400"><HelpCircle className="h-3.5 w-3.5" />Open questions</h3><List items={s.open_questions} empty="None" /></section>
              <details className="rounded-lg border border-ink-200 p-3">
                <summary className="cursor-pointer text-xs font-medium text-ink-600">Full report as Markdown</summary>
                <div className="prose-report mt-3"><ReactMarkdown>{m.report_md}</ReactMarkdown></div>
              </details>
            </div>
            <div>
              <Card>
                <CardHeader title="Action items" icon={CheckSquare} />
                <div className="divide-y divide-ink-950/15">
                  {!s.action_items?.length && <p className="px-4 py-3 text-xs text-ink-400">None</p>}
                  {(s.action_items || []).map((a, i) => (
                    <div key={i} className="px-4 py-2.5 text-sm">
                      <p className="text-ink-800">{a.title}</p>
                      <p className="mt-0.5 text-[11px] text-ink-500">{a.owner_name || 'No owner'}{a.due_date && ` · due ${a.due_date}`}</p>
                    </div>
                  ))}
                </div>
              </Card>
              {s.stats && <div className="mt-3 rounded-lg bg-ink-50 p-3 text-xs text-ink-600">
                <p className="mb-1 font-medium text-ink-800">Progress tracking</p>
                {s.stats.items_created} new work items · {s.stats.items_updated} updated · {s.stats.carried_over} carried over · {s.stats.blockers} new blockers
              </div>}
            </div>
          </div>
        ))}

        {current === 'updates' && (
          <div className="space-y-3 bg-ink-50/50 p-4">
            {!m.updates.length && <Empty title="No individual updates (yet)" />}
            {m.updates.map((u) => <UpdateCard key={u.id} update={u} showMeeting={false} showName canReview={u.employee_id === user.employee_id || user.role !== 'employee'} onChanged={reload} />)}
          </div>
        )}

        {current === 'transcript' && (
          <div className="max-h-[70vh] space-y-2.5 overflow-y-auto p-5">
            {!m.transcript.length && <Empty title="No transcript yet" />}
            {m.transcript.map((t, i) => (
              <div key={i} className="flex gap-3 text-sm">
                <span className="w-11 shrink-0 pt-0.5 text-right font-mono text-[11px] text-ink-400">{mmss(t.start)}</span>
                <div className="min-w-0">
                  <span className="font-medium text-ink-900">{t.speaker}</span>
                  <p className={t.redacted ? 'italic text-ink-400' : 'text-ink-700'}>{t.text}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {current === 'participants' && (
          <div className="divide-y divide-ink-950/15">
            <p className="px-5 py-2.5 text-xs text-ink-500">Display names are matched to employee profiles automatically. Fix a wrong or missing match here - the name is remembered as an alias for next time. Re-analyse afterwards to rebuild the updates.</p>
            {m.participants.map((p) => (
              <div key={p.id} className="flex flex-wrap items-center gap-3 px-5 py-2.5">
                <div className="min-w-0 flex-1">
                  <span className="text-sm font-medium">{p.display_name}</span>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {p.is_bot && <Badge>Bot</Badge>}
                    {p.joined_late && <Badge tone="amber">Joined late</Badge>}
                  </div>
                </div>
                {!p.is_bot && (perms.manage ? (
                  <Select className="w-56" value={p.employee_id || ''} onChange={(e) => act('map', () => api.mapParticipant(id, p.id, { employee_id: e.target.value || null }))}>
                    <option value="">Not linked to anyone</option>
                    {(directory.data || []).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                  </Select>
                ) : <span className="text-sm text-ink-600">{p.employee_name || 'Not linked'}</span>)}
                {p.employee_id && <Link to={`/people/${p.employee_id}`} className="text-xs font-bold text-ink-950 underline decoration-2 underline-offset-2 hover:bg-accent-soft">Profile</Link>}
              </div>
            ))}
            {!m.participants.length && <Empty title="No participants seen yet" />}
          </div>
        )}

        {current === 'activity' && (
          <div className="p-5">
            <ol className="relative space-y-3 border-l border-ink-200 pl-4">
              {(m.consent_events || []).map((e, i) => (
                <li key={i} className="text-sm">
                  <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-ink-950" />
                  <p className="font-medium">{ACTIVITY_LABEL[e.kind] || e.kind}{e.participant && <span className="font-normal text-ink-600"> · {e.participant}</span>}</p>
                  <p className="text-xs text-ink-500">{e.detail} · {fmtDateTime(e.at)}{e.actor !== 'bot' && ` · by ${e.actor}`}</p>
                </li>
              ))}
              {!m.consent_events?.length && <p className="text-sm text-ink-400">Nothing yet.</p>}
            </ol>
          </div>
        )}

        {current === 'sharing' && share && (
          <div className="space-y-4 p-5">
            <ShareFields full={share.full} employee={share.employee} onChange={({ full, employee }) => setShare({ full, employee })} />
            <Button loading={busy === 'share'} onClick={() => act('share', () => api.shareMeeting(id, { share_full: share.full, share_employee: share.employee }))}>Save sharing</Button>
          </div>
        )}
      </Card>
    </>
  )
}
