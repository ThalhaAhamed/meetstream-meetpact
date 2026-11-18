import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertOctagon, ArrowRight, CalendarClock, CheckCircle2, Clock, FolderKanban, Repeat, TrendingUp, Users, Video } from 'lucide-react'
import { api } from '../api'
import {
  Avatar, Badge, BotStatus, Card, CardHeader, Empty, ErrorBox, PageHeader, ProcStatus, Select, Spinner, Stat,
  fmtDateTime, relTime, useLoad,
} from '../components/ui'

function TrendChart({ data }) {
  const max = Math.max(1, ...data.map((d) => Math.max(d.completed, d.created)))
  return (
    <div>
      <div className="flex h-32 items-end gap-1.5">
        {data.map((d) => (
          <div key={d.date} className="group relative flex h-full flex-1 items-end justify-center gap-0.5">
            <div className="w-1/2 border-2 border-b-0 border-ink-950 bg-white" style={{ height: `${(d.created / max) * 100}%`, minHeight: d.created ? 3 : 0 }} />
            <div className="w-1/2 border-2 border-b-0 border-ink-950 bg-pop-mint" style={{ height: `${(d.completed / max) * 100}%`, minHeight: d.completed ? 3 : 0 }} />
            <div className="pointer-events-none absolute -top-9 z-10 hidden whitespace-nowrap rounded bg-ink-900 px-2 py-1 text-[11px] text-white group-hover:block">
              {d.date.slice(5)}: {d.completed} done, {d.created} new
            </div>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] text-ink-400"><span>{data[0]?.date.slice(5)}</span><span>today</span></div>
      <div className="mt-2 flex gap-4 text-[11px] text-ink-500">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-xs border border-ink-950 bg-pop-mint" />Completed</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-xs border border-ink-950 bg-white" />New work items</span>
      </div>
    </div>
  )
}

const ATTN = {
  overdue: ['Overdue', 'bg-pop-red', Clock],
  blocker: ['Blocked', 'bg-pop-yellow', AlertOctagon],
  carried: ['Keeps slipping', 'bg-pop-orange', Repeat],
}

// The focal point: what needs a manager's attention right now.
function NeedsAttention({ items, unreviewed }) {
  if (!items.length) {
    return (
      <Card className="flex items-center gap-4 bg-pop-mint/40 p-5">
        <CheckCircle2 className="h-8 w-8 shrink-0" strokeWidth={2.25} />
        <div>
          <p className="text-lg font-bold">Nothing needs attention</p>
          <p className="text-sm text-ink-700">No overdue work, no open blockers, nothing slipping meeting after meeting.</p>
        </div>
      </Card>
    )
  }
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b-2 border-ink-950 bg-pop-yellow px-5 py-3">
        <h2 className="text-lg font-bold">Needs your attention <span className="font-mono">({items.length})</span></h2>
        {unreviewed > 0 && <span className="text-xs font-bold">{unreviewed} AI updates not yet reviewed by their owners</span>}
      </div>
      <ul className="divide-y-2 divide-ink-950/10">
        {items.map((a, i) => {
          const [label, fill, Icon] = ATTN[a.kind]
          return (
            <li key={i}>
              <Link to={a.employee_id ? `/people/${a.employee_id}` : '/board'} className="group flex items-center gap-3 px-5 py-3 hover:bg-ink-50">
                <span title={label} className={`inline-flex shrink-0 items-center gap-1.5 rounded border-2 border-ink-950 px-1.5 py-0.5 text-[11px] font-bold sm:w-32 ${fill}`}><Icon className="h-3.5 w-3.5" /><span className="hidden sm:inline">{label}</span><span className="sr-only sm:hidden">{label}</span></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-bold">{a.title}</span>
                  <span className="block text-xs text-ink-600">{a.employee_name || 'Unassigned'} · {a.detail}</span>
                </span>
                <ArrowRight className="h-4 w-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
              </Link>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

export default function Dashboard() {
  const [teamId, setTeamId] = useState('')
  const { data, error, loading } = useLoad(() => api.dashboard(teamId || undefined), [teamId])
  const teams = useLoad(() => api.teams(), [])
  const upcoming = useLoad(() => api.upcoming(2), [])

  return (
    <>
      <PageHeader
        title="Team overview"
        subtitle="Progress, commitments and blockers gathered from every meeting"
        actions={
          <Select value={teamId} onChange={(e) => setTeamId(e.target.value)} className="w-44">
            <option value="">All teams</option>
            {(teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        }
      />
      <ErrorBox error={error} />
      {loading && !data ? <Spinner /> : data && (
        <div className="space-y-5">
          <NeedsAttention items={data.attention || []} unreviewed={data.totals.unreviewed} />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <Stat label="People" value={data.totals.employees} />
            <Stat label="Open work items" value={data.totals.open} />
            <Stat label="Done this week" value={data.totals.completed_week} tone={data.totals.completed_week ? 'mint' : undefined} />
            <Stat label="Overdue" value={data.totals.overdue} tone={data.totals.overdue ? 'red' : undefined} />
            <Stat label="Open blockers" value={data.totals.blockers} tone={data.totals.blockers ? 'amber' : undefined} />
            <Stat label="Meetings this week" value={data.totals.meetings_week} hint={`${data.totals.unreviewed} updates awaiting review`} />
          </div>

          <div className="grid gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title="Team members" subtitle="Latest update from each person" icon={Users} />
              <div className="divide-y divide-ink-950/15">
                {data.employees.length === 0 && <Empty icon={Users} title="No people yet">Add employees under Admin.</Empty>}
                {data.employees.map((e) => (
                  <Link key={e.id} to={`/people/${e.id}`} className="flex items-start gap-3 px-5 py-3 hover:bg-ink-50/60">
                    <Avatar name={e.name} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-sm font-medium">{e.name}</span>
                        <span className="text-xs text-ink-400">{e.title}</span>
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-xs text-ink-600">
                        {e.last_update ? e.last_update.summary : <span className="italic text-ink-400">No updates yet</span>}
                      </p>
                      {e.last_update && <p className="mt-0.5 text-[11px] text-ink-400">{e.last_update.meeting_title} · {relTime(e.last_update.created_at)}</p>}
                    </div>
                    <div className="flex shrink-0 flex-wrap justify-end gap-1">
                      <Badge>{e.open} open</Badge>
                      {e.completed_week > 0 && <Badge tone="green">{e.completed_week} done</Badge>}
                      {e.overdue > 0 && <Badge tone="red">{e.overdue} overdue</Badge>}
                      {e.open_blockers > 0 && <Badge tone="amber">{e.open_blockers} blocked</Badge>}
                      {e.carried_over > 0 && <Badge tone="peach">{e.carried_over} carried</Badge>}
                    </div>
                  </Link>
                ))}
              </div>
            </Card>

            <div className="space-y-5">
              <Card>
                <CardHeader title="Last 14 days" icon={TrendingUp} />
                <div className="px-5 py-4"><TrendChart data={data.trend} /></div>
              </Card>
              <Card>
                <CardHeader title="Next 48 hours" icon={CalendarClock} action={<Link to="/schedules" className="text-xs font-bold text-ink-950 underline decoration-2 underline-offset-2 hover:bg-accent-soft">Schedules</Link>} />
                <div className="divide-y divide-ink-950/15">
                  {(upcoming.data || []).slice(0, 5).map((u) => (
                    <div key={u.schedule_id + u.at} className="flex items-center justify-between gap-2 px-5 py-2.5 text-sm">
                      <div className="min-w-0">
                        <p className="truncate font-medium">{u.title}</p>
                        <p className="text-[11px] text-ink-500">{fmtDateTime(u.at)} · {u.mode === 'standup' ? 'AI-led stand-up' : 'Notetaker'}</p>
                      </div>
                    </div>
                  ))}
                  {upcoming.data && !upcoming.data.length && <Empty title="Nothing scheduled" />}
                </div>
              </Card>
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-3">
            <Card>
              <CardHeader title="Open blockers" icon={AlertOctagon} />
              <div className="divide-y divide-ink-950/15">
                {data.blockers.length === 0 && <Empty title="No open blockers" />}
                {data.blockers.map((b) => (
                  <div key={b.id} className="px-5 py-2.5">
                    <p className="text-sm text-ink-800">{b.description}</p>
                    <p className="mt-0.5 text-[11px] text-ink-500">
                      {b.employee_name} · raised {relTime(b.created_at)}{b.mention_count > 1 && ` · mentioned ${b.mention_count}×`}
                    </p>
                  </div>
                ))}
              </div>
            </Card>
            <Card>
              <CardHeader title="Projects" icon={FolderKanban} action={<Link to="/projects" className="text-xs font-bold text-ink-950 underline decoration-2 underline-offset-2 hover:bg-accent-soft">All</Link>} />
              <div className="space-y-3 px-5 py-4">
                {data.projects.length === 0 && <p className="text-sm text-ink-400">No projects yet.</p>}
                {data.projects.map((p) => (
                  <div key={p.id}>
                    <div className="flex justify-between text-sm"><span className="font-medium">{p.name}</span><span className="tabular-nums text-ink-500">{p.percent}%</span></div>
                    <div className="mt-1 h-3 overflow-hidden rounded border-2 border-ink-950 bg-white"><div className="h-full bg-pop-mint" style={{ width: `${p.percent}%` }} /></div>
                    <p className="mt-0.5 text-[11px] text-ink-500">{p.completed}/{p.total} done · {p.in_progress} in progress{p.blocked ? ` · ${p.blocked} blocked` : ''}</p>
                  </div>
                ))}
              </div>
            </Card>
            <Card>
              <CardHeader title="Recent meetings" icon={Video} action={<Link to="/meetings" className="text-xs font-bold text-ink-950 underline decoration-2 underline-offset-2 hover:bg-accent-soft">All</Link>} />
              <div className="divide-y divide-ink-950/15">
                {data.recent_meetings.length === 0 && <Empty title="No meetings yet" />}
                {data.recent_meetings.map((m) => (
                  <Link key={m.id} to={`/meetings/${m.id}`} className="block px-5 py-2.5 hover:bg-ink-50/60">
                    <div className="flex items-center gap-1.5"><span className="truncate text-sm font-medium">{m.title}</span></div>
                    <div className="mt-1 flex items-center gap-1.5 text-[11px] text-ink-500">
                      {fmtDateTime(m.scheduled_at || m.created_at)}
                      {m.processing_status === 'done' ? <ProcStatus status="done" /> : <BotStatus status={m.bot_status} />}
                    </div>
                  </Link>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </>
  )
}
