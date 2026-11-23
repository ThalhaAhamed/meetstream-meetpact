import { useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, ErrorBox, Field, Select, Spinner, cx, useLoad } from './ui'

const STATUS_OPTIONS = [
  ['planned', 'To do'], ['in_progress', 'In progress'], ['blocked', 'Blocked'], ['completed', 'Done'], ['ignore', "Don't track"],
]

// Pick where a team's tasks live: MeetPact's own board or a Trello board,
// map the Trello lists to statuses and the Trello members to people.
export default function TeamBoardSettings({ team, onSaved }) {
  const trello = useLoad(() => api.trello(), [])
  const [source, setSource] = useState(team.board_source || 'native')
  const [boardId, setBoardId] = useState('')
  const [lists, setLists] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(null)
  const connected = trello.data?.connected
  const boards = useLoad(() => (connected && source === 'trello' ? api.trelloBoards() : Promise.resolve([])), [connected, source])
  const live = useLoad(() => (team.board_source === 'trello' ? api.teamBoard(team.id) : Promise.resolve(null)), [team.id, team.board_source])
  const people = useLoad(() => api.employees(), [])

  useEffect(() => {
    if (live.data?.lists) setLists(live.data.lists.map(({ id, name, status }) => ({ id, name, status })))
  }, [live.data])
  useEffect(() => {
    if (!boardId && boards.data?.length && team.board_source === 'trello') {
      const current = boards.data.find((b) => b.name === team.board_name)
      if (current) setBoardId(current.id)
    }
  }, [boards.data])  // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    setBusy(true); setError(null); setDone(null)
    try {
      const r = await api.chooseBoard(team.id, source === 'native' ? { source } :
        { source, board_id: boardId, lists: lists?.map(({ id, status }) => ({ id, status })) })
      if (r.lists) setLists(r.lists)
      setDone(source === 'native' ? 'This team now uses the MeetPact board.'
        : `Connected to "${r.board_name}": ${r.synced.created} cards imported, ${r.synced.updated} updated.`)
      live.reload(); onSaved?.()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  const link = async (memberId, employeeId) => {
    try { await api.linkBoardMember(team.id, { member_id: memberId, employee_id: employeeId || null }); live.reload() } catch (e) { setError(e) }
  }

  return (
    <div className="space-y-3 rounded-md border-2 border-ink-950 bg-ink-50 p-3">
      <p className="text-xs font-bold">Task board</p>
      <div className="grid grid-cols-2 gap-2">
        {[['native', 'MeetPact board', 'Tasks from meetings, kept here'], ['trello', 'Trello board', 'Use the team\'s board in Trello']].map(([k, label, hint]) => (
          <button key={k} type="button" onClick={() => setSource(k)}
            className={cx('rounded-md border-2 p-2 text-left text-sm', source === k ? 'border-ink-950 bg-accent shadow-press' : 'border-ink-300 bg-white')}>
            <span className="block font-bold">{label}</span><span className="text-xs text-ink-600">{hint}</span>
          </button>
        ))}
      </div>

      {source === 'trello' && (!trello.data ? <Spinner inline /> : !connected ? (
        <p className="text-sm text-ink-700">Connect Trello first under <b>Admin → Bot & settings → Trello</b>.</p>
      ) : (
        <>
          <Field label="Board">
            <Select value={boardId} onChange={(e) => { setBoardId(e.target.value); setLists(null) }}>
              <option value="">Choose a board…</option>
              {(boards.data || []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </Select>
          </Field>
          {lists && boardId && (
            <div>
              <p className="mb-1 text-xs font-bold">What each list means</p>
              <div className="space-y-1">
                {lists.map((l, i) => (
                  <div key={l.id} className="flex items-center gap-2 text-sm">
                    <span className="min-w-0 flex-1 truncate">{l.name}</span>
                    <Select className="w-40" value={l.status} onChange={(e) => setLists(lists.map((x, j) => (j === i ? { ...x, status: e.target.value } : x)))}>
                      {STATUS_OPTIONS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                    </Select>
                  </div>
                ))}
              </div>
            </div>
          )}
          {live.data?.members?.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-bold">Trello members</p>
              <div className="space-y-1">
                {live.data.members.map((m) => (
                  <div key={m.id} className="flex items-center gap-2 text-sm">
                    <span className="min-w-0 flex-1 truncate">{m.name}</span>
                    <Select className="w-48" value={m.employee_id || ''} onChange={(e) => link(m.id, e.target.value)}>
                      <option value="">Not a MeetPact person</option>
                      {(people.data || []).filter((p) => p.active).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </Select>
                  </div>
                ))}
              </div>
            </div>
          )}
          {team.board_url && team.board_source === 'trello' && (
            <a href={team.board_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-bold underline decoration-2 underline-offset-2">
              Open "{team.board_name}" in Trello <ExternalLink className="h-3 w-3" /></a>
          )}
        </>
      ))}

      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" loading={busy} disabled={source === 'trello' && (!connected || !boardId)} onClick={save}>
          {source === 'trello' && team.board_source === 'trello' ? 'Save and sync' : 'Use this board'}</Button>
        {team.board_source === 'trello' ? <Badge tone="blue">Trello</Badge> : <Badge>MeetPact</Badge>}
      </div>
      {done && <p className="text-xs font-medium">{done}</p>}
      <ErrorBox error={error} />
    </div>
  )
}
