import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertOctagon, CheckCircle2, ListTodo, Plus, Repeat, Trash2, Video } from 'lucide-react'
import { api } from '../api'
import { useUser } from '../user'
import UpdateCard from '../components/UpdateCard'
import WorkItemModal from '../components/WorkItemModal'
import {
  Avatar, Badge, Button, Card, Empty, ErrorBox, Field, Input, ItemStatus, Modal, PageHeader, ProcStatus, Select,
  Spinner, Stat, Tabs, fmtDate, fmtDateTime, relTime, useLoad,
} from '../components/ui'

function ItemsTable({ items, onOpen }) {
  if (!items.length) return <Empty icon={ListTodo} title="Nothing here" />
  return (
    <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-sm">
      <thead><tr className="border-b border-ink-100 text-left text-[11px] text-ink-400">
        <th className="px-4 py-2 font-medium">Work item</th><th className="px-2 py-2 font-medium">Status</th>
        <th className="px-2 py-2 font-medium">Deadline</th><th className="px-2 py-2 font-medium">Project</th><th className="px-4 py-2 text-right font-medium">Updated</th>
      </tr></thead>
      <tbody className="divide-y divide-ink-950/15">
        {items.map((w) => (
          <tr key={w.id} onClick={() => onOpen(w.id)} className="cursor-pointer hover:bg-ink-50/70">
            <td className="px-4 py-2.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium text-ink-900">{w.title}</span>
                {w.carry_count >= 2 && <Badge tone="violet"><Repeat className="h-3 w-3" />carried {w.carry_count}×</Badge>}
                {w.kind !== 'task' && <Badge>{w.kind === 'action_item' ? 'Action item' : 'Commitment'}</Badge>}
                {w.external && <Badge tone="blue">{w.external.provider}</Badge>}
              </div>
            </td>
            <td className="px-2 py-2.5"><ItemStatus status={w.status} /></td>
            <td className={`px-2 py-2.5 text-xs ${w.overdue ? 'font-semibold text-red-700' : 'text-ink-600'}`}>{w.due_date ? fmtDate(w.due_date) : '—'}{w.overdue && ' · overdue'}</td>
            <td className="px-2 py-2.5 text-xs text-ink-600">{w.project_name || '—'}</td>
            <td className="px-4 py-2.5 text-right text-xs text-ink-500">{relTime(w.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </table></div>
  )
}

export function ProfileView({ data, reload, isSelf }) {
  const user = useUser()
  const [tab, setTab] = useState('open')
  const [openItem, setOpenItem] = useState(null)
  const [adding, setAdding] = useState(null)
  const [error, setError] = useState(null)
  const { employee, work_items, updates, blockers, meetings, stats, can_edit } = data
  const open = work_items.filter((w) => ['planned', 'in_progress', 'blocked'].includes(w.status))
  const done = work_items.filter((w) => w.status === 'completed')
  const canReview = user.employee_id === employee.id || user.role !== 'employee'

  const addItem = async () => {
    try {
      await api.createWorkItem({ ...adding, employee_id: employee.id, due_date: adding.due_date || null })
      setAdding(null)
      reload()
    } catch (e) { setError(e) }
  }
  const navigate = useNavigate()
  const erase = async () => {
    if (window.prompt(`This permanently deletes ${employee.name}'s profile, updates, work items, blockers and transcript lines. Type ERASE to confirm.`) !== 'ERASE') return
    try { await api.eraseEmployee(employee.id); navigate('/people') } catch (e) { setError(e) }
  }
  const resolveBlocker = async (b) => { await api.updateBlocker(b.id, { status: b.status === 'open' ? 'resolved' : 'open' }); reload() }

  return (
    <>
      <PageHeader
        title={<span className="flex items-center gap-3"><Avatar name={employee.name} size={10} />{isSelf ? 'My progress' : employee.name}</span>}
        subtitle={[employee.title, employee.team_name].filter(Boolean).join(' · ') || undefined}
        actions={<>
          {can_edit && <Button icon={Plus} variant="secondary" onClick={() => setAdding({ title: '', status: 'planned', due_date: '' })}>Add work item</Button>}
          {user.role === 'admin' && !isSelf && <Button icon={Trash2} variant="danger" onClick={erase}>Erase all data</Button>}
        </>}
      />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Open" value={stats.open} />
        <Stat label="Completed" value={stats.completed} />
        <Stat label="Overdue" value={stats.overdue} tone={stats.overdue ? 'red' : undefined} />
        <Stat label="Open blockers" value={stats.open_blockers} tone={stats.open_blockers ? 'amber' : undefined} />
        <Stat label="Updates to review" value={stats.unreviewed} hint={isSelf ? 'Confirm or correct what the AI recorded' : undefined} />
      </div>
      <Card>
        <div className="px-4 pt-2">
          <Tabs value={tab} onChange={setTab} tabs={[
            ['open', 'Open work', open.length], ['done', 'Completed', done.length], ['updates', 'Updates', updates.length],
            ['blockers', 'Blockers', blockers.filter((b) => b.status === 'open').length], ['meetings', 'Meetings', meetings.length],
          ]} />
        </div>
        {tab === 'open' && <ItemsTable items={open} onOpen={setOpenItem} />}
        {tab === 'done' && <ItemsTable items={done} onOpen={setOpenItem} />}
        {tab === 'updates' && (
          <div className="space-y-3 bg-ink-50/50 p-4">
            {!updates.length && <Empty title="No meeting updates yet" />}
            {updates.map((u) => <UpdateCard key={u.id} update={u} canReview={canReview} onChanged={reload} />)}
          </div>
        )}
        {tab === 'blockers' && (
          <div className="divide-y divide-ink-950/15">
            {!blockers.length && <Empty icon={AlertOctagon} title="No blockers recorded" />}
            {blockers.map((b) => (
              <div key={b.id} className="flex items-center gap-3 px-4 py-3">
                {b.status === 'open' ? <AlertOctagon className="h-4 w-4 shrink-0 text-amber-600" /> : <CheckCircle2 className="h-4 w-4 shrink-0 text-ink-950" />}
                <div className="min-w-0 flex-1">
                  <p className={`text-sm ${b.status === 'resolved' ? 'text-ink-400 line-through' : ''}`}>{b.description}</p>
                  <p className="text-[11px] text-ink-500">Raised {fmtDate(b.created_at)}{b.mention_count > 1 && ` · mentioned in ${b.mention_count} meetings`}{b.resolved_at && ` · resolved ${fmtDate(b.resolved_at)}`}</p>
                </div>
                {can_edit && <Button size="sm" variant="secondary" onClick={() => resolveBlocker(b)}>{b.status === 'open' ? 'Mark resolved' : 'Reopen'}</Button>}
              </div>
            ))}
          </div>
        )}
        {tab === 'meetings' && (
          <div className="divide-y divide-ink-950/15">
            {!meetings.length && <Empty icon={Video} title="No meetings yet" />}
            {meetings.map((m) => (
              <Link key={m.id} to={`/meetings/${m.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-ink-50/60">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5"><span className="text-sm font-medium">{m.title}</span></div>
                  <p className="line-clamp-1 text-xs text-ink-500">{m.overview || (m.can_view_full ? '' : 'Full report not shared with you - your own section is visible.')}</p>
                </div>
                <span className="text-xs text-ink-500">{fmtDateTime(m.scheduled_at || m.created_at)}</span>
                <ProcStatus status={m.processing_status} />
              </Link>
            ))}
          </div>
        )}
      </Card>
      <WorkItemModal itemId={openItem} onClose={() => setOpenItem(null)} onSaved={reload} canEdit={can_edit} />
      <Modal open={!!adding} onClose={() => setAdding(null)} title="Add work item"
        footer={<><Button variant="secondary" onClick={() => setAdding(null)}>Cancel</Button><Button onClick={addItem} disabled={!adding?.title}>Add</Button></>}>
        {adding && <>
          <Field label="Title"><Input autoFocus value={adding.title} onChange={(e) => setAdding({ ...adding, title: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Status"><Select value={adding.status} onChange={(e) => setAdding({ ...adding, status: e.target.value })}>
              <option value="planned">Planned</option><option value="in_progress">In progress</option><option value="blocked">Blocked</option><option value="completed">Done</option>
            </Select></Field>
            <Field label="Deadline"><Input type="date" value={adding.due_date} onChange={(e) => setAdding({ ...adding, due_date: e.target.value })} /></Field>
          </div>
          <ErrorBox error={error} />
        </>}
      </Modal>
    </>
  )
}

export default function EmployeeProfile() {
  const { id } = useParams()
  const { data, error, loading, reload } = useLoad(() => api.employeeProfile(id), [id])
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Spinner />
  return <ProfileView data={data} reload={reload} isSelf={false} />
}
