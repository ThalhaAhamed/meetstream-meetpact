import { useState } from 'react'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { api } from '../api'
import WorkItemModal from './WorkItemModal'
import { Avatar, Badge, Button, ErrorBox, Spinner, cx, fmtDate, relTime, useLoad } from './ui'

const TINT = {
  planned: 'bg-ink-100/60', in_progress: 'bg-pop-sky/30', blocked: 'bg-pop-yellow/30', completed: 'bg-pop-mint/30', ignore: 'bg-white',
}

// A team's Trello board, live: lists in Trello's order, cards with the people
// assigned to them. Dragging a card moves it in Trello.
export default function TrelloBoard({ teamId, canEdit }) {
  const board = useLoad(() => api.teamBoard(teamId), [teamId])
  const [dragging, setDragging] = useState(null)
  const [over, setOver] = useState(null)
  const [openItem, setOpenItem] = useState(null)
  const [error, setError] = useState(null)
  const b = board.data

  const drop = async (listId) => {
    const card = dragging
    setDragging(null); setOver(null)
    if (!card || card.listId === listId) return
    board.setData((d) => ({
      ...d, lists: d.lists.map((l) => ({
        ...l, cards: l.id === listId ? [...l.cards, card.card] : l.cards.filter((c) => c.id !== card.card.id),
      })),
    }))
    try { await api.moveCard(teamId, { card_id: card.card.id, list_id: listId }) } catch (e) { setError(e); board.reload() }
  }

  if (board.loading && !b) return <Spinner label="Loading the Trello board…" />
  if (board.error) return <ErrorBox error={board.error} />
  if (!b) return null

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <Badge tone="blue">Trello</Badge>
        <span className="font-bold">{b.board_name}</span>
        {b.board_url && <a href={b.board_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-bold underline decoration-2 underline-offset-2 hover:bg-accent-soft">Open in Trello <ExternalLink className="h-3 w-3" /></a>}
        <span className="text-xs text-ink-500">· synced {relTime(b.synced_at)}</span>
        <Button size="sm" variant="ghost" icon={RefreshCw} className="ml-auto" loading={board.loading} onClick={board.reload}>Refresh</Button>
      </div>
      <ErrorBox error={error} />
      <div className="-mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-4 sm:mx-0 sm:px-0">
        {b.lists.map((l) => (
          <section key={l.id} aria-label={l.name}
            onDragOver={(e) => { e.preventDefault(); setOver(l.id) }} onDragLeave={() => setOver(null)} onDrop={() => drop(l.id)}
            className={cx('flex min-h-[220px] w-[78vw] shrink-0 snap-start flex-col rounded-lg border-2 border-ink-950 p-2 transition-shadow sm:w-72',
              TINT[l.status] || 'bg-white', over === l.id ? 'shadow-lift' : 'shadow-card', l.status === 'ignore' && 'opacity-70')}>
            <h2 className="mb-2 flex items-center justify-between gap-2 px-1 text-sm font-bold">
              <span className="truncate">{l.name}</span>
              <span className="rounded border-2 border-ink-950 bg-white px-1.5 font-mono text-xs">{l.cards.length}</span>
            </h2>
            <div className="flex flex-1 flex-col gap-2">
              {l.cards.map((c) => (
                <article key={c.id} draggable={canEdit} onDragStart={() => setDragging({ card: c, listId: l.id })}
                  onDragEnd={() => { setDragging(null); setOver(null) }}
                  onClick={() => c.item_id && setOpenItem(c.item_id)}
                  className={cx('rounded-md border-2 border-ink-950 bg-white p-2.5 text-sm shadow-press transition-transform hover:-translate-y-px',
                    c.item_id && 'cursor-pointer', dragging?.card.id === c.id && 'opacity-50')}>
                  <div className="flex items-start gap-2">
                    <p className="min-w-0 flex-1 font-bold leading-snug">{c.title}</p>
                    {c.url && <a href={c.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} aria-label="Open card in Trello"
                      className="shrink-0 rounded p-0.5 text-ink-500 hover:bg-accent-soft hover:text-ink-950"><ExternalLink className="h-3.5 w-3.5" /></a>}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {c.members.length ? c.members.map((m) => (
                      <span key={m.id || m.name} className="flex items-center gap-1 text-[11px] font-medium"
                        title={m.meetpact_only ? `${m.name} (owner in MeetPact; not added to the card in Trello)` : m.employee_id ? m.name : `${m.name} (not linked to a MeetPact person)`}>
                        <Avatar name={m.name} size={6} />{m.name.split(' ')[0]}
                      </span>
                    )) : <span className="text-[11px] font-medium text-ink-500">Unassigned</span>}
                    {c.due && <Badge tone={c.done ? 'green' : c.overdue ? 'red' : 'gray'}>{c.done ? 'Done ' : c.overdue ? 'Overdue ' : 'Due '}{fmtDate(c.due, { month: 'short', day: 'numeric' })}</Badge>}
                  </div>
                </article>
              ))}
              {!l.cards.length && <p className="px-1 py-6 text-center text-xs text-ink-500">No cards</p>}
            </div>
          </section>
        ))}
      </div>
      <WorkItemModal itemId={openItem} onClose={() => setOpenItem(null)} onSaved={board.reload} canEdit={!!openItem && canEdit} />
    </>
  )
}
