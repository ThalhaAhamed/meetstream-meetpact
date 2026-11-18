import { useState } from 'react'
import { Copy, Download } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'
import { Button, Card, ErrorBox, Field, Input, PageHeader, Select, Spinner, Stat, Tabs, useLoad } from '../components/ui'

export default function Reports() {
  const [params, setParams] = useState({ period: 'weekly', anchor: new Date().toISOString().slice(0, 10), team_id: '', project_id: '', employee_id: '' })
  const [view, setView] = useState('summary')
  const teams = useLoad(() => api.teams(), [])
  const projects = useLoad(() => api.projects(), [])
  const people = useLoad(() => api.employees(), [])
  const { data, error, loading } = useLoad(() => api.periodReport(params), [JSON.stringify(params)])
  const set = (k) => (e) => setParams({ ...params, [k]: e.target.value })

  const download = () => {
    const blob = new Blob([data.markdown], { type: 'text/markdown' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${data.period}-report-${data.start}.md`
    a.click()
  }

  return (
    <>
      <PageHeader title="Reports" subtitle="Daily, weekly and monthly progress, by team, project or person"
        actions={data && <><Button variant="secondary" icon={Copy} onClick={() => navigator.clipboard.writeText(data.markdown)}>Copy</Button><Button variant="secondary" icon={Download} onClick={download}>Download .md</Button></>} />
      <Card className="mb-5 grid gap-3 p-4 sm:grid-cols-5">
        <Field label="Period"><Select value={params.period} onChange={set('period')}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></Select></Field>
        <Field label="Containing date"><Input type="date" value={params.anchor} onChange={set('anchor')} /></Field>
        <Field label="Team"><Select value={params.team_id} onChange={set('team_id')}><option value="">All</option>{(teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
        <Field label="Project"><Select value={params.project_id} onChange={set('project_id')}><option value="">All</option>{(projects.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
        <Field label="Person"><Select value={params.employee_id} onChange={set('employee_id')}><option value="">Everyone</option>{(people.data || []).filter((e) => e.active).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
      </Card>
      <ErrorBox error={error} />
      {loading && !data ? <Spinner /> : data && (
        <>
          <p className="mb-3 text-sm text-ink-600"><span className="font-medium text-ink-900">{data.scope}</span> · {data.start} to {data.end}</p>
          <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-6">
            <Stat label="Meetings" value={data.totals.meetings} /><Stat label="Completed" value={data.totals.completed} />
            <Stat label="New items" value={data.totals.new} /><Stat label="Open" value={data.totals.open} />
            <Stat label="Overdue" value={data.totals.overdue} tone={data.totals.overdue ? 'red' : undefined} />
            <Stat label="Open blockers" value={data.totals.blockers} tone={data.totals.blockers ? 'amber' : undefined} />
          </div>
          <Card>
            <div className="px-4 pt-2"><Tabs value={view} onChange={setView} tabs={[['summary', 'By person'], ['markdown', 'Formatted report']]} /></div>
            {view === 'summary' ? (
              <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-sm">
                <thead><tr className="border-b border-ink-100 text-left text-[11px] text-ink-400">
                  <th className="px-4 py-2">Person</th><th className="px-2 py-2">Updates</th><th className="px-2 py-2">Completed</th><th className="px-2 py-2">Open</th><th className="px-2 py-2">Overdue</th><th className="px-4 py-2">Blockers</th>
                </tr></thead>
                <tbody className="divide-y divide-ink-950/15">
                  {data.employees.map((e) => (
                    <tr key={e.employee_id} className="align-top">
                      <td className="px-4 py-2.5 font-medium">{e.name}</td>
                      <td className="px-2 py-2.5 tabular-nums">{e.updates}</td>
                      <td className="px-2 py-2.5"><span className="tabular-nums">{e.completed.length}</span>{e.completed.length > 0 && <p className="line-clamp-2 text-[11px] text-ink-500">{e.completed.join(', ')}</p>}</td>
                      <td className="px-2 py-2.5 tabular-nums">{e.open.length}</td>
                      <td className="px-2 py-2.5 tabular-nums text-red-700">{e.overdue.length || ''}</td>
                      <td className="px-4 py-2.5 text-xs text-ink-600">{e.blockers.join('; ') || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            ) : <div className="prose-report p-5"><ReactMarkdown>{data.markdown}</ReactMarkdown></div>}
          </Card>
        </>
      )}
    </>
  )
}
