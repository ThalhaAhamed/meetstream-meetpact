import { useState } from 'react'
import { ExternalLink, Link2, Unlink } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, ErrorBox, Field, Input, Spinner, useLoad } from './ui'

const link = 'font-bold underline decoration-2 underline-offset-2 hover:bg-accent-soft'

// Connect a Trello account in two steps: the Power-Up API key, then the token
// Trello shows after "Allow". Used in Admin and in the setup wizard.
export default function TrelloConnect({ onChange, canEdit = true }) {
  const status = useLoad(() => api.trello(), [])
  const [key, setKey] = useState('')
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const s = status.data

  const run = async (fn) => {
    setBusy(true); setError(null)
    try { await fn(); await status.reload(); onChange?.() } catch (e) { setError(e) } finally { setBusy(false) }
  }

  if (!s) return <Spinner inline label="Checking Trello…" />
  if (s.connected) return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge tone="green">Connected</Badge> as <b>{s.account}</b>
      {canEdit && !s.from_env && <Button size="sm" variant="ghost" icon={Unlink} loading={busy}
        onClick={() => window.confirm('Disconnect Trello? Team boards stop syncing until it is connected again.') && run(api.disconnectTrello)}>Disconnect</Button>}
      {s.from_env && <span className="text-xs text-ink-500">(set in .env)</span>}
    </div>
  )
  if (!canEdit) return <p className="text-sm text-ink-600">Trello is not connected yet. An admin can connect it.</p>
  return (
    <div className="space-y-3">
      {s.error && <ErrorBox error={s.error} />}
      {!s.has_key ? (
        <>
          <p className="text-sm text-ink-700">
            1. Open <a className={link} href="https://trello.com/power-ups/admin" target="_blank" rel="noreferrer">trello.com/power-ups/admin <ExternalLink className="inline h-3 w-3" /></a>,
            create a Power-Up (any name, leave the iframe URL empty), open its <b>API key</b> tab and generate a key.
          </p>
          <Field label="Trello API key"><Input value={key} onChange={(e) => setKey(e.target.value)} placeholder="32 characters" /></Field>
          <Button size="sm" icon={Link2} loading={busy} disabled={key.trim().length < 20}
            onClick={() => run(() => api.saveTrello({ api_key: key.trim() }))}>Next</Button>
        </>
      ) : (
        <>
          <p className="text-sm text-ink-700">
            2. <a className={link} href={s.authorize_url} target="_blank" rel="noreferrer">Allow MeetPact on Trello <ExternalLink className="inline h-3 w-3" /></a>,
            click <b>Allow</b>, and paste the token Trello shows (it starts with <code className="font-mono text-xs">ATTA</code>).
          </p>
          <Field label="Trello token"><Input value={token} onChange={(e) => setToken(e.target.value)} placeholder="ATTA…" /></Field>
          <div className="flex gap-2">
            <Button size="sm" loading={busy} disabled={token.trim().length < 20}
              onClick={() => run(() => api.saveTrello({ token: token.trim() }))}>Connect</Button>
            <Button size="sm" variant="ghost" onClick={() => run(api.disconnectTrello)}>Use another key</Button>
          </div>
        </>
      )}
      <ErrorBox error={error} />
    </div>
  )
}
