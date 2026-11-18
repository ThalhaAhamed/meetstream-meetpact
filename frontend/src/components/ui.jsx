import { useEffect, useState, useCallback } from 'react'
import { X, Loader2, AlertTriangle } from 'lucide-react'

export function cx(...c) { return c.filter(Boolean).join(' ') }

export function Card({ className, children, ...rest }) {
  // White unless the caller passes its own background colour.
  const bg = /(^|\s)bg-/.test(className || '') ? '' : 'bg-white'
  return <div className={cx('rounded-lg border-2 border-ink-950 shadow-card', bg, className)} {...rest}>{children}</div>
}

export function CardHeader({ title, subtitle, action, icon: Icon }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b-2 border-ink-950 px-5 py-3">
      <div className="flex min-w-0 items-center gap-2.5">
        {Icon && <Icon className="h-4 w-4 shrink-0 text-ink-950" strokeWidth={2.25} />}
        <div className="min-w-0">
          <h3 className="truncate text-sm font-bold text-ink-950">{title}</h3>
          {subtitle && <p className="truncate text-xs text-ink-500">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

const BUTTON = {
  primary: 'border-2 border-ink-950 bg-pop-yellow text-ink-950 shadow-press hover:-translate-x-px hover:-translate-y-px hover:shadow-card active:translate-x-0.5 active:translate-y-0.5 active:shadow-none disabled:opacity-50',
  secondary: 'border-2 border-ink-950 bg-white text-ink-950 shadow-press hover:-translate-x-px hover:-translate-y-px hover:shadow-card active:translate-x-0.5 active:translate-y-0.5 active:shadow-none disabled:opacity-50',
  ghost: 'border-2 border-transparent text-ink-800 hover:border-ink-950 hover:bg-white',
  danger: 'border-2 border-ink-950 bg-pop-red text-ink-950 shadow-press hover:-translate-x-px hover:-translate-y-px hover:shadow-card active:translate-x-0.5 active:translate-y-0.5 active:shadow-none',
}

export function Button({ variant = 'primary', size = 'md', className, icon: Icon, loading, children, ...rest }) {
  return (
    <button
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-md font-bold transition-[background-color,box-shadow,transform] duration-150 ease-out disabled:cursor-not-allowed disabled:transform-none focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500',
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm',
        BUTTON[variant], className,
      )}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className={size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4'} /> : null}
      {children}
    </button>
  )
}

const TONES = {
  gray: 'bg-white',
  green: 'bg-pop-mint',
  blue: 'bg-pop-sky',
  amber: 'bg-pop-yellow',
  red: 'bg-pop-red',
  violet: 'bg-pop-lilac',
}

export function Badge({ tone = 'gray', children, className }) {
  return <span className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded border-2 border-ink-950 px-1.5 py-px text-[11px] font-bold text-ink-950', TONES[tone], className)}>{children}</span>
}

const ITEM_STATUS = {
  planned: ['gray', 'Planned'], in_progress: ['blue', 'In progress'], blocked: ['red', 'Blocked'],
  completed: ['green', 'Done'], dropped: ['gray', 'Dropped'],
}
export function ItemStatus({ status }) {
  const [tone, label] = ITEM_STATUS[status] || ['gray', status]
  return <Badge tone={tone}>{label}</Badge>
}

const BOT_STATUS = {
  pending: ['gray', 'Pending'], scheduled: ['violet', 'Scheduled'], joining: ['amber', 'Joining'],
  waiting_room: ['amber', 'In waiting room'], in_meeting: ['blue', 'In meeting'], recording: ['red', '● Recording'],
  paused: ['amber', 'Paused'], ended: ['gray', 'Ended'], not_admitted: ['red', 'Not admitted'], denied: ['red', 'Denied'],
  failed: ['red', 'Failed'], cancelled: ['gray', 'Cancelled'], imported: ['violet', 'Imported'],
}
const PROC_STATUS = {
  waiting: ['gray', 'Waiting for transcript'], fetching: ['amber', 'Fetching transcript'], analysing: ['amber', 'Analysing'],
  done: ['green', 'Report ready'], failed: ['red', 'Processing failed'], skipped: ['gray', 'No report'],
}
export function BotStatus({ status }) {
  const [tone, label] = BOT_STATUS[status] || ['gray', status]
  return <Badge tone={tone}>{label}</Badge>
}
export function ProcStatus({ status }) {
  const [tone, label] = PROC_STATUS[status] || ['gray', status]
  return <Badge tone={tone}>{label}</Badge>
}

// Page-level loading: a skeleton shaped like the cards/lists that follow,
// instead of a lone spinner. `inline` keeps the small spinner for tight spots.
export function Spinner({ label = 'Loading…', inline = false }) {
  if (inline) return <div className="flex items-center gap-2 p-6 text-sm text-ink-500"><Loader2 className="h-4 w-4 animate-spin" />{label}</div>
  return (
    <div role="status" aria-live="polite" className="space-y-4 py-2">
      <span className="sr-only">{label}</span>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="h-[76px] rounded-lg border-2 border-ink-950 bg-white p-4 shadow-card"><div className="skeleton h-3 w-20" /><div className="skeleton mt-3 h-6 w-12" /></div>)}
      </div>
      <div className="rounded-lg border-2 border-ink-950 bg-white p-5 shadow-card">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex items-center gap-3 py-2.5">
            <div className="skeleton h-8 w-8 rounded-lg" />
            <div className="flex-1 space-y-2"><div className="skeleton h-3 w-1/3" /><div className="skeleton h-3 w-2/3" /></div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ErrorBox({ error }) {
  if (!error) return null
  return (
    <div role="alert" className="flex items-start gap-2 rounded-md border-2 border-ink-950 bg-pop-red/40 px-3 py-2 text-sm font-medium text-ink-950 shadow-press">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{String(error.message || error)}</span>
    </div>
  )
}

export function Empty({ icon: Icon, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      {Icon && <span className="mb-3 inline-flex rounded-md border-2 border-ink-950 bg-pop-yellow p-2 shadow-press"><Icon className="h-5 w-5" strokeWidth={2.25} /></span>}
      <p className="text-sm font-bold text-ink-950">{title}</p>
      {children && <div className="mt-1 max-w-sm text-xs text-ink-500">{children}</div>}
    </div>
  )
}

export function Modal({ open, onClose, title, children, footer, wide }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-950/50 p-4 pt-[8vh]" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" className={cx('w-full animate-fade-up rounded-lg border-2 border-ink-950 bg-white shadow-lift', wide ? 'max-w-3xl' : 'max-w-lg')} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between rounded-t-md border-b-2 border-ink-950 bg-pop-yellow px-5 py-3">
          <h2 className="text-base font-bold">{title}</h2>
          <button onClick={onClose} className="rounded border-2 border-transparent p-1 text-ink-950 hover:border-ink-950 hover:bg-white" aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        <div className="space-y-4 px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t-2 border-ink-950 px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-bold text-ink-950">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-ink-500">{hint}</span>}
    </label>
  )
}

const INPUT = 'rounded-md border-2 border-ink-950 bg-white px-3 py-2 text-sm placeholder:text-ink-400 transition-shadow focus:shadow-press focus:outline-none disabled:bg-ink-100 disabled:text-ink-500'
// Full width unless the caller sets its own width class.
const width = (c) => (/(^|\s)w-/.test(c || '') ? '' : 'w-full')
export const Input = (p) => <input {...p} className={cx(INPUT, width(p.className), p.className)} />
export const Textarea = (p) => <textarea {...p} className={cx(INPUT, 'min-h-[90px]', width(p.className), p.className)} />
export const Select = ({ children, ...p }) => <select {...p} className={cx(INPUT, 'pr-8', width(p.className), p.className)}>{children}</select>

export function Stat({ label, value, tone, hint }) {
  return (
    // Flat colour fill only when the number needs attention.
    <Card className={cx('px-4 py-3', tone === 'red' ? 'bg-pop-red' : tone === 'amber' ? 'bg-pop-yellow' : 'bg-white')}>
      <p className="text-xs font-bold text-ink-950">{label}</p>
      <p className="mt-1 font-mono text-3xl font-bold tabular-nums text-ink-950">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] font-medium text-ink-700">{hint}</p>}
    </Card>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex flex-wrap gap-2 py-2">
      {tabs.map(([key, label, count]) => (
        <button key={key} onClick={() => onChange(key)}
          className={cx('rounded-md border-2 px-3 py-1 text-sm font-bold transition-[background-color,box-shadow] duration-150',
            value === key ? 'border-ink-950 bg-pop-yellow shadow-press' : 'border-transparent text-ink-700 hover:border-ink-950 hover:bg-white')}>
          {label}{count !== undefined && <span className="ml-1.5 rounded border border-ink-950 bg-white px-1 font-mono text-[11px]">{count}</span>}
        </button>
      ))}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-[-0.03em] text-ink-950 sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm font-medium text-ink-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function List({ items, empty = 'None' }) {
  if (!items || !items.length) return <p className="text-xs italic text-ink-400">{empty}</p>
  return <ul className="space-y-1">{items.map((t, i) => <li key={i} className="flex gap-2 text-sm text-ink-700"><span className="mt-[7px] h-1.5 w-1.5 shrink-0 bg-ink-950" />{t}</li>)}</ul>
}

export function Avatar({ name, size = 8 }) {
  const initials = (name || '?').split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()
  const hue = [...(name || '')].reduce((a, c) => a + c.charCodeAt(0), 0) % 360
  return (
    <span aria-hidden="true" className={cx('inline-flex shrink-0 items-center justify-center rounded-md border-2 border-ink-950 text-[11px] font-bold text-ink-950',size === 8 ? 'h-8 w-8' : size === 6 ? 'h-6 w-6 text-[10px]' : 'h-10 w-10 text-sm')}
      style={{ background: `hsl(${hue} 85% 76%)` }}>{initials}</span>
  )
}

// Small data hook: returns {data, error, loading, reload}.
export function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true }))
    return fn().then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { load() }, [load])
  return { ...state, reload: load, setData: (d) => setState((s) => ({ ...s, data: typeof d === 'function' ? d(s.data) : d })) }
}

export function fmtDate(iso, opts) {
  if (!iso) return '—'
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso)
  return d.toLocaleDateString(undefined, opts || { month: 'short', day: 'numeric', year: 'numeric' })
}
export function fmtDateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
export function relTime(iso) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  const abs = Math.abs(diff)
  const f = (n, u) => `${Math.round(n)} ${u}${Math.round(n) === 1 ? '' : 's'}`
  const s = abs < 60 ? 'just now' : abs < 3600 ? f(abs / 60, 'min') : abs < 86400 ? f(abs / 3600, 'hour') : f(abs / 86400, 'day')
  if (s === 'just now') return s
  return diff >= 0 ? `${s} ago` : `in ${s}`
}
