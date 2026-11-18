import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CalendarDays, Link2, Unlink } from 'lucide-react'
import { api } from '../api'
import { useUser } from '../user'
import { Badge, BotStatus, Button, Card, CardHeader, Empty, ErrorBox, Field, Input, Modal, Select, Spinner, fmtDateTime, useLoad } from './ui'

const split = (s) => s.split(',').map((x) => x.trim()).filter(Boolean)

// Calendar auto-join: connect through MeetStream, pick which meetings the bot joins.
export default function CalendarPanel() {
  const user = useUser()
  const status = useLoad(() => api.calendar(), [])
  const connected = status.data?.connected
  const events = useLoad(() => (connected ? api.calendarEvents(72) : Promise.resolve([])), [connected])
  const [connect, setConnect] = useState(null)
  const [filters, setFilters] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  // Back from Google sign-in: /schedules?calendar=connected or ?calendar_error=...
  const [params, setParams] = useSearchParams()
  const signInError = params.get('calendar_error')
  const justConnected = params.get('calendar') === 'connected'
  const clearParams = () => setParams((p) => { p.delete('calendar'); p.delete('calendar_error'); return p }, { replace: true })

  const act = async (name, fn) => {
    setBusy(name); setError(null)
    try { await fn(); status.reload(); events.reload() } catch (e) { setError(e) } finally { setBusy(null) }
  }
  const s = status.data

  return (
    <Card className="mt-6">
      <CardHeader title="Calendar auto-join" icon={CalendarDays}
        subtitle={connected ? `Connected: ${s.account}` : 'Connect Google or Outlook so the bot joins calendar meetings without pasting links'}
        action={user.role === 'admin' && (connected
          ? <Button size="sm" variant="ghost" icon={Unlink} loading={busy === 'dc'} onClick={() => window.confirm('Disconnect the calendar? MeetStream deletes the synced events and cancels calendar bots.') && act('dc', api.disconnectCalendar)}>Disconnect</Button>
          : s?.google_sign_in
            ? <a href="/api/calendar/google/start" className="inline-flex items-center gap-1.5 rounded-md border-2 border-ink-950 bg-accent px-2.5 py-1 text-xs font-bold text-ink-950 shadow-press hover:-translate-x-px hover:-translate-y-px hover:shadow-card"><Link2 className="h-3.5 w-3.5" />Connect Google Calendar</a>
            : <Button size="sm" icon={Link2} onClick={() => setConnect({ provider: 'google', client_id: '', client_secret: '', refresh_token: '' })}>Connect calendar</Button>)} />
      <div className="space-y-4 p-5">
        <ErrorBox error={error || events.error || signInError} />
        {justConnected && connected && (
          <p className="flex items-center justify-between gap-2 rounded-md border-2 border-ink-950 bg-pop-mint/50 px-3 py-2 text-sm font-medium">
            Calendar connected. Turn on auto-join below to have the bot join its meetings.
            <button className="text-xs font-bold underline" onClick={clearParams}>Dismiss</button></p>
        )}
        {!s ? <Spinner inline /> : !connected ? (
          <div className="space-y-2 text-sm text-ink-700">
            {s.google_sign_in
              ? <p>Sign in with Google to connect. MeetPact asks for read-only calendar access and passes the token to MeetStream, which keeps the calendar in sync; it is not stored here.</p>
              : <p>Set <code className="font-mono text-xs">GOOGLE_CLIENT_ID</code> and <code className="font-mono text-xs">GOOGLE_CLIENT_SECRET</code> in .env for a one-click Google sign-in (see docs/integrations.md), or connect with a refresh token.</p>}
            {s.google_sign_in && user.role === 'admin' && (
              <button className="text-xs font-bold underline decoration-2 underline-offset-2 hover:bg-accent-soft"
                onClick={() => setConnect({ provider: 'outlook', client_id: '', client_secret: '', refresh_token: '' })}>Outlook, or connect with a refresh token instead</button>)}
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 rounded-md border-2 border-ink-950 bg-ink-50 p-3">
              <label className="flex items-center gap-2 text-sm font-bold">
                <input type="checkbox" className="h-4 w-4 accent-ink-950" checked={s.auto_join} disabled={busy === 'auto'}
                  onChange={(e) => act('auto', () => api.setCalendarAutoJoin({ auto_join: e.target.checked, include_keywords: s.include_keywords, exclude_keywords: s.exclude_keywords }))} />
                Join calendar meetings automatically
              </label>
              <span className="text-xs text-ink-600">
                {s.include_keywords.length ? `only titles with: ${s.include_keywords.join(', ')}` : 'all meetings with a link'}
                {s.exclude_keywords.length ? ` · skipping: ${s.exclude_keywords.join(', ')}` : ''}
              </span>
              <Button size="sm" variant="secondary" className="ml-auto" onClick={() => setFilters({ include: s.include_keywords.join(', '), exclude: s.exclude_keywords.join(', ') })}>Filters</Button>
            </div>
            {events.loading && !events.data ? <Spinner inline /> : !events.data?.length ? (
              <Empty icon={CalendarDays} title="No meetings in the next 3 days" />
            ) : (
              <ul className="divide-y-2 divide-ink-950/10 rounded-md border-2 border-ink-950">
                {events.data.map((ev) => (
                  <li key={ev.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold">{ev.title}</p>
                      <p className="text-xs text-ink-600">{fmtDateTime(ev.start)} · {ev.platform || 'meeting'}{!ev.meeting_url && ' · no meeting link'}</p>
                    </div>
                    {ev.meeting ? (
                      <Link to={`/meetings/${ev.meeting.id}`}><BotStatus status={ev.meeting.bot_status} /></Link>
                    ) : ev.meeting_url ? (
                      <>
                        {s.auto_join && ev.auto_join_match && <Badge tone="green">Will auto-join</Badge>}
                        {s.auto_join && !ev.auto_join_match && <Badge>Filtered out</Badge>}
                        <Button size="sm" variant="secondary" loading={busy === ev.id} onClick={() => act(ev.id, () => api.joinCalendarEvent(ev.id))}>Send bot</Button>
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      <Modal open={!!connect} onClose={() => setConnect(null)} title="Connect a calendar"
        footer={<><Button variant="secondary" onClick={() => setConnect(null)}>Cancel</Button>
          <Button loading={busy === 'connect'} disabled={!connect?.client_id || !connect?.client_secret || !connect?.refresh_token}
            onClick={() => act('connect', async () => { await api.connectCalendar(connect); setConnect(null) })}>Connect</Button></>}>
        {connect && <>
          <Field label="Provider"><Select value={connect.provider} onChange={(e) => setConnect({ ...connect, provider: e.target.value })}>
            <option value="google">Google Calendar</option><option value="outlook">Outlook / Microsoft 365</option></Select></Field>
          <Field label="OAuth client ID"><Input value={connect.client_id} onChange={(e) => setConnect({ ...connect, client_id: e.target.value })} /></Field>
          <Field label="OAuth client secret"><Input type="password" value={connect.client_secret} onChange={(e) => setConnect({ ...connect, client_secret: e.target.value })} /></Field>
          <Field label="Refresh token" hint="Sent to MeetStream, which keeps the calendar in sync. Not stored here.">
            <Input type="password" value={connect.refresh_token} onChange={(e) => setConnect({ ...connect, refresh_token: e.target.value })} /></Field>
          <ErrorBox error={error} />
        </>}
      </Modal>

      <Modal open={!!filters} onClose={() => setFilters(null)} title="Which meetings to join"
        footer={<><Button variant="secondary" onClick={() => setFilters(null)}>Cancel</Button>
          <Button onClick={() => act('filters', async () => { await api.setCalendarAutoJoin({ auto_join: s.auto_join, include_keywords: split(filters.include), exclude_keywords: split(filters.exclude) }); setFilters(null) })}>Save</Button></>}>
        {filters && <>
          <Field label="Only join meetings whose title contains" hint="Comma separated. Empty = every meeting with a link.">
            <Input value={filters.include} onChange={(e) => setFilters({ ...filters, include: e.target.value })} placeholder="stand-up, sync, review" /></Field>
          <Field label="Never join meetings whose title contains" hint="Comma separated.">
            <Input value={filters.exclude} onChange={(e) => setFilters({ ...filters, exclude: e.target.value })} /></Field>
        </>}
      </Modal>
    </Card>
  )
}
