import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { FileText, ListTodo, MessageSquareQuote, Sparkles } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Input, ItemStatus, PageHeader, fmtDate } from '../components/ui'

const EXAMPLES = [
  'What did Priya commit to this week?',
  'Which tasks keep getting carried over?',
  'What is blocking the mobile team?',
  'What was decided about the invoice export?',
]

export default function Ask() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') || '')
  const [answer, setAnswer] = useState(null)
  const [found, setFound] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const run = async (question) => {
    const text = (question ?? q).trim()
    if (text.length < 3) return
    setQ(text); setParams({ q: text }); setBusy(true); setError(null); setAnswer(null)
    api.search(text).then(setFound).catch(() => setFound(null))
    try { setAnswer(await api.ask(text)) } catch (e) { setError(e) } finally { setBusy(false) }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (params.get('q')) run(params.get('q')) }, [])

  return (
    <>
      <PageHeader title="Ask & search" subtitle="Answers come only from meetings and records you're allowed to see" />
      <form onSubmit={(e) => { e.preventDefault(); run() }} className="mb-4 flex gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask anything about your team's work…" className="text-base" />
        <Button type="submit" icon={Sparkles} loading={busy}>Ask</Button>
      </form>
      {!answer && !busy && !error && (
        <div className="mb-6 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => <button key={ex} onClick={() => run(ex)} className="rounded-md border-2 border-ink-950 bg-white px-2.5 py-1 text-xs font-bold shadow-press hover:bg-pop-yellow">{ex}</button>)}
        </div>
      )}
      <ErrorBox error={error} />
      {(busy || answer) && (
        <Card className="mb-6 bg-pop-mint/30">
          <CardHeader title="Answer" icon={Sparkles} action={answer && <span className="text-[11px] font-medium text-ink-600">from {answer.sources} records</span>} />
          <div className="prose-report px-5 py-4">
            {busy ? <div className="space-y-2"><div className="skeleton h-3 w-3/4" /><div className="skeleton h-3 w-2/3" /><div className="skeleton h-3 w-1/2" /></div>
              : <ReactMarkdown>{answer.answer}</ReactMarkdown>}
          </div>
        </Card>
      )}
      {found && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader title="Work items" icon={ListTodo} />
            <div className="divide-y divide-ink-950/15">
              {!found.work_items.length && <Empty title="No matching work items" />}
              {found.work_items.map((w) => (
                <Link key={w.id} to={w.employee_id ? `/people/${w.employee_id}` : '/board'} className="flex items-center gap-2 px-5 py-2.5 hover:bg-pop-yellow/30">
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{w.title}</span>
                  <span className="text-xs text-ink-500">{w.employee_name}</span><ItemStatus status={w.status} />
                </Link>
              ))}
            </div>
          </Card>
          <Card>
            <CardHeader title="Meetings and updates" icon={FileText} />
            <div className="divide-y divide-ink-950/15">
              {!found.meetings.length && !found.updates.length && <Empty title="No matching meetings" />}
              {found.updates.slice(0, 8).map((u) => (
                <Link key={u.id} to={`/meetings/${u.meeting_id}`} className="block px-5 py-2.5 hover:bg-pop-yellow/30">
                  <p className="text-sm"><span className="font-bold">{u.employee_name}</span> · {u.meeting_title} <span className="text-xs text-ink-500">{fmtDate(u.meeting_date)}</span></p>
                  <p className="line-clamp-2 text-xs text-ink-600">{u.summary}</p>
                </Link>
              ))}
              {found.meetings.slice(0, 5).map((m) => (
                <Link key={m.id} to={`/meetings/${m.id}`} className="flex items-center gap-2 px-5 py-2.5 hover:bg-pop-yellow/30">
                  <span className="flex-1 text-sm font-medium">{m.title}</span><Badge>Meeting</Badge>
                </Link>
              ))}
            </div>
          </Card>
          {found.transcript.length > 0 && (
            <Card className="lg:col-span-2">
              <CardHeader title="Said in meetings" icon={MessageSquareQuote} />
              <div className="divide-y divide-ink-950/15">
                {found.transcript.slice(0, 8).map((t, i) => (
                  <Link key={i} to={`/meetings/${t.meeting_id}`} className="block px-5 py-2.5 hover:bg-pop-yellow/30">
                    <p className="text-xs text-ink-500">{t.meeting_title} · {fmtDate(t.date)} · <span className="font-bold text-ink-900">{t.speaker}</span></p>
                    <p className="line-clamp-2 text-sm">“{t.text}”</p>
                  </Link>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </>
  )
}
