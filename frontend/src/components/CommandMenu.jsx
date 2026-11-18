import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CornerDownLeft, FileText, ListTodo, Sparkles, UserRound } from 'lucide-react'
import { api } from '../api'
import { cx } from './ui'

// Ctrl/Cmd+K: jump to a page, a person, a meeting or a work item, or ask a question.
export default function CommandMenu({ open, onClose, nav }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [people, setPeople] = useState([])
  const [active, setActive] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return
    setQ(''); setResults([]); setActive(0)
    setTimeout(() => inputRef.current?.focus(), 0)
    api.directory().then(setPeople).catch(() => {})
  }, [open])

  // Debounced server search for meetings and work items.
  useEffect(() => {
    if (!open || q.trim().length < 3) { setResults([]); return }
    const t = setTimeout(() => {
      api.search(q).then((r) => setResults([
        ...r.meetings.slice(0, 5).map((m) => ({ kind: 'Meeting', label: m.title, to: `/meetings/${m.id}`, icon: FileText })),
        ...r.work_items.slice(0, 6).map((w) => ({ kind: 'Work item', label: `${w.title}${w.employee_name ? ` - ${w.employee_name}` : ''}`, to: w.employee_id ? `/people/${w.employee_id}` : '/board', icon: ListTodo })),
      ])).catch(() => setResults([]))
    }, 200)
    return () => clearTimeout(t)
  }, [q, open])

  const items = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const pages = nav.filter(([, label]) => !needle || label.toLowerCase().includes(needle))
      .map(([to, label, Icon]) => ({ kind: 'Page', label, to, icon: Icon }))
    const ppl = needle ? people.filter((p) => p.name.toLowerCase().includes(needle)).slice(0, 5)
      .map((p) => ({ kind: 'Person', label: p.name, to: `/people/${p.id}`, icon: UserRound })) : []
    const ask = needle.length > 3 ? [{ kind: 'Ask', label: `Ask: "${q.trim()}"`, to: `/ask?q=${encodeURIComponent(q.trim())}`, icon: Sparkles }] : []
    return [...ask, ...pages, ...ppl, ...results]
  }, [q, nav, people, results])

  useEffect(() => { setActive(0) }, [items.length])
  if (!open) return null

  const go = (item) => { onClose(); navigate(item.to) }
  const onKey = (e) => {
    if (e.key === 'Escape') onClose()
    else if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter' && items[active]) go(items[active])
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-ink-950/50 p-4 pt-[12vh]" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Command menu" className="w-full max-w-xl animate-fade-up rounded-lg border-2 border-ink-950 bg-white shadow-lift" onMouseDown={(e) => e.stopPropagation()}>
        <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
          placeholder="Search people, meetings, work - or ask a question"
          className="w-full rounded-t-md border-b-2 border-ink-950 bg-pop-yellow/30 px-4 py-3 text-base font-medium outline-none placeholder:text-ink-500" />
        <ul className="max-h-[50vh] overflow-y-auto p-2" role="listbox">
          {items.length === 0 && <li className="px-3 py-6 text-center text-sm text-ink-500">Type at least 3 letters to search meetings and work items.</li>}
          {items.map((it, i) => {
            const Icon = it.icon
            return (
              <li key={it.kind + it.label + i} role="option" aria-selected={i === active}>
                <button onMouseEnter={() => setActive(i)} onClick={() => go(it)}
                  className={cx('flex w-full items-center gap-3 rounded-md border-2 px-3 py-2 text-left text-sm',
                    i === active ? 'border-ink-950 bg-pop-yellow font-bold shadow-press' : 'border-transparent')}>
                  <Icon className="h-4 w-4 shrink-0" strokeWidth={2.25} />
                  <span className="min-w-0 flex-1 truncate">{it.label}</span>
                  <span className="shrink-0 text-[11px] font-medium text-ink-500">{it.kind}</span>
                  {i === active && <CornerDownLeft className="h-3.5 w-3.5 shrink-0" />}
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
