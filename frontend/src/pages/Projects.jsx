import { useState } from 'react'
import { FolderKanban } from 'lucide-react'
import { api } from '../api'
import WorkItemModal from '../components/WorkItemModal'
import { Badge, Card, Empty, ErrorBox, ItemStatus, PageHeader, Spinner, cx, fmtDate, useLoad } from '../components/ui'
import { useUser, isManager } from '../user'

const COLUMNS = [['planned', 'Planned'], ['in_progress', 'In progress'], ['blocked', 'Blocked'], ['completed', 'Done']]

export default function Projects() {
  const user = useUser()
  const { data, error, loading } = useLoad(() => api.projectsProgress(), [])
  const [selected, setSelected] = useState(null)
  const items = useLoad(() => (selected ? api.projectItems(selected) : Promise.resolve([])), [selected])
  const [openItem, setOpenItem] = useState(null)
  const current = (data || []).find((p) => p.id === selected)

  return (
    <>
      <PageHeader title="Projects" subtitle="Work items are attributed to projects from what is said in meetings" />
      <ErrorBox error={error} />
      {loading && !data ? <Spinner /> : !data.length ? <Card><Empty icon={FolderKanban} title="No projects yet">Create projects under Admin, with keywords that identify them in conversation.</Empty></Card> : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {data.map((p) => (
            <button key={p.id} onClick={() => setSelected(p.id === selected ? null : p.id)} className="text-left">
              <Card className={cx('p-4 transition-shadow duration-200 hover:shadow-lift', selected === p.id && '-translate-x-0.5 -translate-y-0.5 bg-pop-yellow shadow-lift')}>
                <div className="flex items-center justify-between"><p className="font-medium">{p.name}</p><Badge tone={p.status === 'active' ? 'green' : 'gray'}>{p.status}</Badge></div>
                <p className="mt-0.5 line-clamp-1 text-xs text-ink-500">{p.description || '—'}</p>
                <div className="mt-3 flex items-end justify-between"><span className="text-2xl font-semibold tabular-nums">{p.percent}%</span><span className="text-xs text-ink-500">{p.completed}/{p.total} done</span></div>
                <div className="mt-1.5 h-3 overflow-hidden rounded border-2 border-ink-950 bg-white"><div className="h-full bg-pop-mint" style={{ width: `${p.percent}%` }} /></div>
                <p className="mt-2 text-[11px] text-ink-500">{p.in_progress} in progress · {p.blocked} blocked · {p.open_blockers} open blockers · {p.members} people</p>
              </Card>
            </button>
          ))}
        </div>
      )}
      {current && (
        <div className="mt-6">
          <h2 className="mb-3 text-sm font-semibold">{current.name} - work board</h2>
          <div className="grid gap-3 md:grid-cols-4">
            {COLUMNS.map(([k, label]) => {
              const col = (items.data || []).filter((w) => w.status === k)
              return (
                <div key={k} className="rounded-xl bg-ink-100/70 p-2">
                  <p className="mb-2 px-1 text-xs font-semibold text-ink-600">{label} <span className="text-ink-400">{col.length}</span></p>
                  <div className="space-y-2">
                    {col.map((w) => (
                      <button key={w.id} onClick={() => setOpenItem(w.id)} className="block w-full rounded-lg border border-ink-200 bg-white p-2.5 text-left text-sm shadow-sm hover:border-ink-300">
                        <p className="font-medium text-ink-800">{w.title}</p>
                        <p className="mt-1 text-[11px] text-ink-500">{w.employee_name || 'Unassigned'}{w.due_date && ` · ${fmtDate(w.due_date, { month: 'short', day: 'numeric' })}`}</p>
                        {w.overdue && <Badge tone="red" className="mt-1">Overdue</Badge>}
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
      <WorkItemModal itemId={openItem} onClose={() => setOpenItem(null)} onSaved={items.reload} canEdit={isManager(user)} />
    </>
  )
}
