import { useState } from 'react'
import { CalendarClock, Pencil, Plus, Trash2 } from 'lucide-react'
import { api } from '../api'
import ShareFields from '../components/ShareFields'
import CalendarPanel from '../components/CalendarPanel'
import {
  Badge, Button, Card, Empty, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, cx, fmtDateTime, useLoad,
} from '../components/ui'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const today = () => new Date().toISOString().slice(0, 10)

const blank = () => ({
  title: '', meeting_link: '', mode: 'notetaker', recurrence: 'weekdays', days_of_week: [0, 1, 2, 3, 4],
  time_of_day: '09:30', timezone: tz, start_date: today(), end_date: '', duration_minutes: 30, team_id: '', project_id: '',
  share_full: { audience: 'participants', user_ids: [] }, share_employee: { audience: 'managers', user_ids: [] }, active: true,
})

function describe(s) {
  const r = s.recurrence === 'once' ? `Once on ${s.start_date}` : s.recurrence === 'daily' ? 'Every day'
    : s.recurrence === 'weekdays' ? 'Weekdays' : `Weekly on ${s.days_of_week.map((d) => DAYS[d]).join(', ')}`
  return `${r} at ${s.time_of_day} (${s.timezone})`
}

export default function Schedules() {
  const { data, error, loading, reload } = useLoad(() => api.schedules(), [])
  const teams = useLoad(() => api.teams(), [])
  const projects = useLoad(() => api.projects(), [])
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState(null)

  const save = async () => {
    setBusy(true); setFormError(null)
    const body = { ...form, team_id: form.team_id || null, project_id: form.project_id || null, end_date: form.end_date || null }
    try {
      form.id ? await api.updateSchedule(form.id, body) : await api.createSchedule(body)
      setForm(null); reload()
    } catch (e) { setFormError(e) } finally { setBusy(false) }
  }
  const remove = async (s) => {
    if (!window.confirm(`Delete "${s.title}"? Bots already booked for it are cancelled.`)) return
    await api.deleteSchedule(s.id); reload()
  }
  const toggleDay = (d) => {
    const set = new Set(form.days_of_week)
    set.has(d) ? set.delete(d) : set.add(d)
    setForm({ ...form, days_of_week: [...set].sort() })
  }

  return (
    <>
      <PageHeader title="Schedules" subtitle="Recurring meetings the bot joins on its own - several per day are fine"
        actions={<Button icon={Plus} onClick={() => { setFormError(null); setForm(blank()) }}>New schedule</Button>} />
      <ErrorBox error={error} />
      <Card>
        {loading && !data ? <Spinner /> : !data.length ? (
          <Empty icon={CalendarClock} title="No schedules yet">For example a stand-up at 09:30 on weekdays, or a weekly sync on Fridays. Add as many as you need.</Empty>
        ) : (
          <div className="divide-y divide-ink-950/15">
            {data.map((s) => (
              <div key={s.id} className="flex flex-wrap items-center gap-4 px-5 py-3.5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-medium">{s.title}</span>
                    <Badge tone={s.mode === 'standup' ? 'blue' : 'gray'}>{s.mode === 'standup' ? 'AI-led stand-up' : 'Notetaker'}</Badge>
                    {!s.active && <Badge tone="red">Paused</Badge>}
                  </div>
                  <p className="mt-0.5 text-xs text-ink-500">{describe(s)}</p>
                </div>
                <div className="text-right text-xs text-ink-500">
                  {s.active && s.next.length ? <>Next: <span className="font-medium text-ink-700">{fmtDateTime(s.next[0])}</span></> : 'No upcoming runs'}
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" icon={Pencil} onClick={() => { setFormError(null); setForm({ ...s, end_date: s.end_date || '', team_id: s.team_id || '', project_id: s.project_id || '' }) }}>Edit</Button>
                  <Button size="sm" variant="ghost" icon={Trash2} onClick={() => remove(s)} />
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      <p className="mt-3 text-xs text-ink-500">The server books each occurrence with MeetStream a few minutes ahead (<code>join_at</code>), so keep the backend running. For stand-ups the agent is briefed with everyone's open commitments at that moment.</p>
      <CalendarPanel />

      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? 'Edit schedule' : 'New schedule'} wide
        footer={<><Button variant="secondary" onClick={() => setForm(null)}>Cancel</Button><Button onClick={save} loading={busy} disabled={!form?.title || !form?.meeting_link}>Save</Button></>}>
        {form && <>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Title"><Input autoFocus value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Daily stand-up" /></Field>
            <Field label="Meeting link" hint="A recurring Zoom / Meet / Teams link."><Input value={form.meeting_link} onChange={(e) => setForm({ ...form, meeting_link: e.target.value })} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Mode"><Select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>
              <option value="notetaker">Notetaker (listens)</option><option value="standup">AI-led stand-up (asks each person)</option></Select></Field>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Repeats"><Select value={form.recurrence} onChange={(e) => setForm({ ...form, recurrence: e.target.value })}>
              <option value="weekdays">Weekdays</option><option value="daily">Every day</option><option value="weekly">Weekly on…</option><option value="once">Once</option></Select></Field>
            <Field label="Time"><Input type="time" value={form.time_of_day} onChange={(e) => setForm({ ...form, time_of_day: e.target.value })} /></Field>
            <Field label="Timezone"><Input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></Field>
          </div>
          {form.recurrence === 'weekly' && (
            <div className="flex gap-1.5">
              {DAYS.map((d, i) => <button key={d} type="button" onClick={() => toggleDay(i)} className={cx('rounded-lg border px-2.5 py-1 text-xs font-medium',
                form.days_of_week.includes(i) ? 'border-ink-950 bg-accent shadow-press' : 'border-ink-950 bg-white text-ink-600')}>{d}</button>)}
            </div>
          )}
          <div className="grid grid-cols-4 gap-3">
            <Field label={form.recurrence === 'once' ? 'Date' : 'Starts'}><Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
            {form.recurrence !== 'once' ? <Field label="Ends (optional)"><Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field> : <div />}
            <Field label="Team"><Select value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value })}><option value="">—</option>{(teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
            <Field label="Project"><Select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}><option value="">—</option>{(projects.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
          </div>
          {form.mode === 'standup' && <p className="rounded-md border-2 border-ink-950 bg-pop-sky/40 px-3 py-2 text-xs text-ink-950">The stand-up agent goes through the team roster (the selected team, or everyone) one person at a time, and follows up on what each person committed to last time.</p>}
          <ShareFields full={form.share_full} employee={form.share_employee} onChange={({ full, employee }) => setForm({ ...form, share_full: full, share_employee: employee })} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} className="h-4 w-4 rounded-sm border-2 border-ink-950 accent-ink-950" />Active</label>
          <ErrorBox error={formError} />
        </>}
      </Modal>
    </>
  )
}
