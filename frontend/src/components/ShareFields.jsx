import { useEffect, useState } from 'react'
import { api } from '../api'
import { Field, Select } from './ui'

const OPTIONS = [
  ['organizer', 'Only the organizer'],
  ['participants', 'All meeting participants'],
  ['managers', 'Managers and team leads'],
  ['selected', 'Specific people'],
]

function Audience({ label, hint, value, onChange, users }) {
  const v = value || { audience: 'participants', user_ids: [] }
  const toggle = (id) => {
    const ids = new Set(v.user_ids || [])
    ids.has(id) ? ids.delete(id) : ids.add(id)
    onChange({ ...v, user_ids: [...ids] })
  }
  return (
    <div>
      <Field label={label} hint={hint}>
        <Select value={v.audience} onChange={(e) => onChange({ ...v, audience: e.target.value })}>
          {OPTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </Select>
      </Field>
      {v.audience === 'selected' && (
        <div className="mt-2 max-h-36 space-y-1 overflow-y-auto rounded-lg border border-ink-200 p-2">
          {users.map((u) => (
            <label key={u.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={(v.user_ids || []).includes(u.id)} onChange={() => toggle(u.id)} className="h-4 w-4 rounded-sm border-2 border-ink-950 accent-ink-950" />
              {u.name} <span className="text-xs text-ink-400">{u.email}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

// Two separate audiences: the whole meeting report, and each person's section.
export default function ShareFields({ full, employee, onChange }) {
  const [users, setUsers] = useState([])
  useEffect(() => { api.users().then(setUsers).catch(() => {}) }, [])
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Audience label="Who can see the full meeting report" hint="Summary, decisions, action items and transcript."
        value={full} users={users} onChange={(v) => onChange({ full: v, employee })} />
      <Audience label="Who can see individual employee updates" hint="Each person always sees their own update."
        value={employee} users={users} onChange={(v) => onChange({ full, employee: v })} />
    </div>
  )
}
