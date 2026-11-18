import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Pencil } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, ErrorBox, Field, Input, List, Textarea, fmtDate } from './ui'

const SECTIONS = [
  ['completed', 'Completed'], ['in_progress', 'In progress'], ['planned', 'Planned next'],
  ['pending', 'Still pending'], ['blockers', 'Blockers'],
]

const REVIEW = { unreviewed: ['amber', 'Not reviewed'], confirmed: ['green', 'Confirmed'], corrected: ['blue', 'Corrected'] }

// One person's update from one meeting, with confirm / correct controls.
export default function UpdateCard({ update, canReview, onChanged, showMeeting = true, showName = false }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [tone, label] = REVIEW[update.review_status] || REVIEW.unreviewed

  const startEdit = () => {
    setForm({ summary: update.summary, note: update.employee_note || '',
      ...Object.fromEntries(SECTIONS.map(([k]) => [k, (update[k] || []).join('\n')])) })
    setEditing(true)
  }
  const send = async (body) => {
    setBusy(true)
    setError(null)
    try { await api.reviewUpdate(update.id, body); setEditing(false); onChanged?.() } catch (e) { setError(e) } finally { setBusy(false) }
  }
  const saveCorrection = () => send({
    review_status: 'corrected', employee_note: form.note, summary: form.summary,
    ...Object.fromEntries(SECTIONS.map(([k]) => [k, form[k].split('\n').map((s) => s.trim()).filter(Boolean)])),
  })

  return (
    <div className="rounded-lg border border-ink-200 bg-white p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {showName && <span className="text-sm font-semibold">{update.employee_name}</span>}
        {showMeeting && <Link to={`/meetings/${update.meeting_id}`} className="text-sm font-medium text-ink-900 hover:bg-pop-yellow">{update.meeting_title}</Link>}
        <span className="text-xs text-ink-500">{fmtDate(update.meeting_date || update.created_at)}</span>
        <Badge tone={tone} className="ml-auto">{label}</Badge>
      </div>
      {!editing ? (
        <>
          <p className="text-sm text-ink-700">{update.summary}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {SECTIONS.map(([k, l]) => (
              <div key={k}>
                <p className="mb-1 text-[11px] font-semibold text-ink-400">{l}</p>
                <List items={update[k]} empty="—" />
              </div>
            ))}
          </div>
          {update.commitments?.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-[11px] font-semibold text-ink-400">Commitments</p>
              <List items={update.commitments.map((c) => c.text + (c.due_date ? ` (by ${c.due_date})` : ''))} />
            </div>
          )}
          {update.employee_note && <p className="mt-3 rounded bg-sky-50 px-2 py-1.5 text-xs text-sky-800">Note from {update.employee_name?.split(' ')[0]}: {update.employee_note}</p>}
          {canReview && (
            <div className="mt-3 flex gap-2">
              {update.review_status !== 'confirmed' && <Button size="sm" variant="secondary" icon={Check} loading={busy} onClick={() => send({ review_status: 'confirmed', employee_note: update.employee_note })}>Looks right</Button>}
              <Button size="sm" variant="ghost" icon={Pencil} onClick={startEdit}>Correct</Button>
            </div>
          )}
        </>
      ) : (
        <div className="space-y-3">
          <Field label="Summary"><Textarea value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></Field>
          <div className="grid gap-3 sm:grid-cols-2">
            {SECTIONS.map(([k, l]) => (
              <Field key={k} label={l} hint="One per line"><Textarea value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></Field>
            ))}
            <Field label="Note for your manager"><Input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="What the AI got wrong" /></Field>
          </div>
          <ErrorBox error={error} />
          <div className="flex gap-2"><Button size="sm" onClick={saveCorrection} loading={busy}>Save correction</Button><Button size="sm" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button></div>
        </div>
      )}
      {!editing && <ErrorBox error={error} />}
    </div>
  )
}
