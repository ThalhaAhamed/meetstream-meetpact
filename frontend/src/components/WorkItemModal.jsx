import { useEffect, useState } from 'react'
import { ExternalLink, History, Send } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Button, ErrorBox, Field, Input, ItemStatus, Modal, Select, Spinner, Textarea, fmtDateTime } from './ui'

const KIND_LABEL = { created: 'Created', status_changed: 'Status changed', mentioned: 'Mentioned', carried_over: 'Carried over',
  due_changed: 'Deadline changed', corrected: 'Corrected', synced: 'Synced' }

export default function WorkItemModal({ itemId, onClose, onSaved, canEdit }) {
  const [item, setItem] = useState(null)
  const [form, setForm] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [integrations, setIntegrations] = useState([])

  useEffect(() => {
    if (!itemId) return
    setItem(null)
    api.workItem(itemId).then((i) => {
      setItem(i)
      setForm({ title: i.title, status: i.status, due_date: i.due_date || '', details: i.details || '', note: '' })
    }).catch(setError)
    api.integrations().then((list) => setIntegrations(list.filter((p) => p.configured))).catch(() => {})
  }, [itemId])

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.updateWorkItem(itemId, { title: form.title, status: form.status, details: form.details, note: form.note,
        due_date: form.due_date || null, clear_due: !form.due_date && !!item.due_date })
      onSaved?.()
      onClose()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  const push = async (provider) => {
    setBusy(true)
    try { await api.pushWorkItem(itemId, provider); setItem(await api.workItem(itemId)); onSaved?.() } catch (e) { setError(e) } finally { setBusy(false) }
  }
  const sync = async () => {
    setBusy(true)
    try { await api.syncWorkItem(itemId); setItem(await api.workItem(itemId)); onSaved?.() } catch (e) { setError(e) } finally { setBusy(false) }
  }

  return (
    <Modal open={!!itemId} onClose={onClose} title="Work item" wide
      footer={canEdit && item && <><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy}>Save correction</Button></>}>
      {!item ? (error ? <ErrorBox error={error} /> : <Spinner />) : (
        <div className="grid gap-5 md:grid-cols-5">
          <div className="space-y-3 md:col-span-3">
            <Field label="Title"><Input value={form.title} disabled={!canEdit} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Status">
                <Select value={form.status} disabled={!canEdit} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  <option value="planned">Planned</option><option value="in_progress">In progress</option>
                  <option value="blocked">Blocked</option><option value="completed">Done</option><option value="dropped">Dropped</option>
                </Select>
              </Field>
              <Field label="Deadline"><Input type="date" value={form.due_date} disabled={!canEdit} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></Field>
            </div>
            <Field label="Details"><Textarea value={form.details} disabled={!canEdit} onChange={(e) => setForm({ ...form, details: e.target.value })} /></Field>
            {canEdit && <Field label="Why the change?" hint="Stored in the item's history."><Input value={form.note} placeholder="e.g. AI misheard the deadline" onChange={(e) => setForm({ ...form, note: e.target.value })} /></Field>}
            <div className="rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-600">
              <p>{item.employee_name || 'Unassigned'}{item.project_name && ` · ${item.project_name}`} · {item.source === 'ai' ? 'Recorded by AI' : 'Added by hand'}</p>
              {item.created_meeting_id && <Link className="font-bold text-ink-950 underline decoration-2 underline-offset-2 hover:bg-pop-yellow" to={`/meetings/${item.created_meeting_id}`} onClick={onClose}>Open the meeting it came from</Link>}
            </div>
            <div className="rounded-lg border border-ink-200 p-3">
              <p className="mb-2 text-xs font-medium text-ink-700">Task tool</p>
              {item.external ? (
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="capitalize">{item.external.provider}</span>
                  <span className="text-ink-500">status: {item.external.status || 'unknown'}</span>
                  {item.external.url && <a href={item.external.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-bold text-ink-950 underline decoration-2 underline-offset-2 hover:bg-pop-yellow">Open <ExternalLink className="h-3 w-3" /></a>}
                  <Button size="sm" variant="secondary" onClick={sync} loading={busy}>Sync status</Button>
                </div>
              ) : integrations.length ? (
                <div className="flex flex-wrap gap-2">
                  {integrations.map((p) => <Button key={p.name} size="sm" variant="secondary" icon={Send} disabled={!canEdit} onClick={() => push(p.name)}>Create in {p.label}</Button>)}
                </div>
              ) : <p className="text-xs text-ink-500">No task tool configured. Add ClickUp, Jira, Asana, Trello or monday.com keys in <code>.env</code>.</p>}
            </div>
            <ErrorBox error={error} />
          </div>
          <div className="md:col-span-2">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-ink-700"><History className="h-3.5 w-3.5" />History across meetings</p>
            <ol className="relative space-y-3 border-l border-ink-200 pl-4">
              {item.history.map((h, i) => (
                <li key={i} className="text-xs">
                  <span className="absolute -left-[5px] mt-1 h-2.5 w-2.5 rounded-full border-2 border-white bg-ink-950" />
                  <p className="font-medium text-ink-800">{KIND_LABEL[h.kind] || h.kind}{h.to && <> → <ItemStatus status={h.to} /></>}</p>
                  {h.note && <p className="text-ink-600">{h.note}</p>}
                  <p className="text-ink-400">{fmtDateTime(h.at)}{h.meeting_title ? ` · ${h.meeting_title}` : ''}{h.actor && h.actor !== 'ai' ? ` · ${h.actor}` : ''}</p>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </Modal>
  )
}
