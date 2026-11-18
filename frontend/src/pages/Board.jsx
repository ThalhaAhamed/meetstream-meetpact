import { useMemo, useState } from 'react'
import { Repeat } from 'lucide-react'
import { api } from '../api'
import TrelloBoard from '../components/TrelloBoard'
import WorkItemModal from '../components/WorkItemModal'
import { Avatar, Badge, ErrorBox, PageHeader, Select, Spinner, cx, fmtDate, useLoad } from '../components/ui'
import { useUser, isManager } from '../user'

const COLUMNS = [
  ['planned', 'Planned', 'bg-ink-100/60'],
  ['in_progress', 'In progress', 'bg-pop-sky/30'],
  ['blocked', 'Blocked', 'bg-pop-yellow/30'],
  ['completed', 'Done', 'bg-pop-mint/30'],
]

export default function Board() {
  const user = useUser()
  const [teamId, setTeamId] = useState(() => { try { return localStorage.getItem('board-team') || '' } catch { return '' } })
  const [person, setPerson] = useState('')
  const [project, setProject] = useState('')
  const [dragging, setDragging] = useState(null)
  const [over, setOver] = useState(null)
  const [openItem, setOpenItem] = useState(null)
  const [error, setError] = useState(null)
  const items = useLoad(() => api.workItems({ employee_id: person || undefined, project_id: project || undefined }), [person, project])
  const people = useLoad(() => api.employees(), [])
  const projects = useLoad(() => api.projects(), [])
  const teams = useLoad(() => api.teams(), [])
  const team = (teams.data || []).find((t) => t.id === teamId)
  const onTrello = team?.board_source === 'trello'
  const myTeam = (people.data || []).find((e) => e.id === user.employee_id)?.team_id
  const pickTeam = (id) => { setTeamId(id); try { localStorage.setItem('board-team', id) } catch { /* private mode */ } }
  const teamMembers = new Set((people.data || []).filter((e) => e.team_id === teamId).map((e) => e.id))

  // Only recently finished work in the Done column, so it stays readable.
  const cols = useMemo(() => {
    const cutoff = Date.now() - 14 * 864e5
    const rows = (items.data || []).filter((w) => w.status !== 'dropped' && (!teamId || teamMembers.has(w.employee_id)) &&
      (w.status !== 'completed' || !w.completed_at || new Date(w.completed_at).getTime() > cutoff))
    return Object.fromEntries(COLUMNS.map(([k]) => [k, rows.filter((w) => w.status === k)]))
  }, [items.data, teamId, people.data])

  const canEdit = (w) => isManager(user) || w.employee_id === user.employee_id
  const drop = async (status) => {
    const w = dragging
    setDragging(null); setOver(null)
    if (!w || w.status === status || !canEdit(w)) return
    items.setData((list) => list.map((x) => (x.id === w.id ? { ...x, status } : x)))  // optimistic
    try { await api.updateWorkItem(w.id, { status, note: 'Moved on the work board' }) } catch (e) { setError(e); items.reload() }
  }

  return (
    <>
      <PageHeader title="Work board" subtitle={onTrello ? `${team.name} keeps its tasks on Trello. Drag a card to move it there.` : 'Everything people committed to in meetings. Drag a card to change its status.'}
        actions={<>
          <Select value={teamId} onChange={(e) => pickTeam(e.target.value)} className="w-52" aria-label="Team">
            <option value="">All teams</option>
            {(teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}{t.board_source === 'trello' ? ' · Trello' : ''}</option>)}
          </Select>
          {!onTrello && <>
          <Select value={person} onChange={(e) => setPerson(e.target.value)} className="w-44">
            <option value="">Everyone</option>
            {(people.data || []).filter((e) => e.active).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </Select>
          <Select value={project} onChange={(e) => setProject(e.target.value)} className="w-44">
            <option value="">All projects</option>
            {(projects.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
          </>}
        </>} />
      {onTrello ? <TrelloBoard teamId={team.id} canEdit={isManager(user) || myTeam === team.id} /> : <>
      <ErrorBox error={error || items.error} />
      {items.loading && !items.data ? <Spinner /> : (
        <div className="-mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-4 sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:px-0 xl:grid-cols-4">
          {COLUMNS.map(([key, label, tint]) => (
            <section key={key} aria-label={label}
              onDragOver={(e) => { e.preventDefault(); setOver(key) }} onDragLeave={() => setOver(null)} onDrop={() => drop(key)}
              className={cx('flex min-h-[220px] w-[80vw] shrink-0 snap-start flex-col rounded-lg border-2 border-ink-950 p-2 transition-shadow sm:w-auto', tint,
                over === key ? 'shadow-lift' : 'shadow-card')}>
              <h2 className="mb-2 flex items-center justify-between px-1 text-sm font-bold">
                {label}<span className="rounded border-2 border-ink-950 bg-white px-1.5 font-mono text-xs">{cols[key].length}</span>
              </h2>
              <div className="flex flex-1 flex-col gap-2">
                {cols[key].map((w) => (
                  <article key={w.id} draggable={canEdit(w)} onDragStart={() => setDragging(w)} onDragEnd={() => { setDragging(null); setOver(null) }}
                    onClick={() => setOpenItem(w.id)}
                    className={cx('cursor-pointer rounded-md border-2 border-ink-950 bg-white p-2.5 text-sm shadow-press transition-transform hover:-translate-y-px',
                      dragging?.id === w.id && 'opacity-50', canEdit(w) && 'active:cursor-grabbing')}>
                    <p className="font-bold leading-snug">{w.title}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {w.employee_name && <span className="flex items-center gap-1 text-[11px] font-medium"><Avatar name={w.employee_name} size={6} />{w.employee_name.split(' ')[0]}</span>}
                      {w.due_date && <Badge tone={w.overdue ? 'red' : 'gray'}>{w.overdue ? 'Overdue ' : 'Due '}{fmtDate(w.due_date, { month: 'short', day: 'numeric' })}</Badge>}
                      {w.carry_count >= 2 && <Badge tone="peach"><Repeat className="h-3 w-3" />{w.carry_count}×</Badge>}
                      {w.project_name && <span className="text-[11px] text-ink-500">{w.project_name}</span>}
                    </div>
                  </article>
                ))}
                {!cols[key].length && <p className="px-1 py-6 text-center text-xs text-ink-500">Nothing here</p>}
              </div>
            </section>
          ))}
        </div>
      )}
      <WorkItemModal itemId={openItem} onClose={() => setOpenItem(null)} onSaved={items.reload}
        canEdit={!!openItem && (isManager(user) || (items.data || []).find((w) => w.id === openItem)?.employee_id === user.employee_id)} />
      </>}
    </>
  )
}
