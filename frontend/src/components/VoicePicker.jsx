import { useEffect, useState } from 'react'
import { Check, ExternalLink } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, ErrorBox, Field, Select, Spinner, cx, useLoad } from './ui'

// Choose the AI stand-up host's voice: Gemini Live, OpenAI, Grok or Claude,
// and check with MeetStream that the account can use it.
export default function VoicePicker({ canEdit = true }) {
  const data = useLoad(() => api.voices(), [])
  const [pick, setPick] = useState(null)
  const [busy, setBusy] = useState(null)
  const [result, setResult] = useState(null)
  useEffect(() => { if (data.data && !pick) setPick(data.data.current) }, [data.data])  // eslint-disable-line react-hooks/exhaustive-deps

  if (!data.data || !pick) return <Spinner inline />
  const presets = data.data.presets
  const preset = presets.find((p) => p.name === pick.name) || presets[0]
  const saved = data.data.current
  const dirty = saved.name !== pick.name || saved.voice !== pick.voice

  const run = async (what) => {
    setBusy(what); setResult(null)
    try {
      if (dirty || what === 'save') await api.chooseVoice({ provider: pick.name, voice: pick.voice })
      const r = what === 'check' ? await api.checkVoice() : { message: 'Saved. The next stand-up uses this voice.' }
      setResult({ ok: true, text: r.message }); data.reload()
    } catch (e) { setResult({ ok: false, text: String(e.message || e) }) } finally { setBusy(null) }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        {presets.map((p) => (
          <button key={p.name} type="button" disabled={!canEdit}
            onClick={() => { setPick({ name: p.name, voice: p.default_voice }); setResult(null) }}
            className={cx('rounded-md border-2 p-3 text-left text-sm', pick.name === p.name ? 'border-ink-950 bg-accent shadow-press' : 'border-ink-300 bg-white')}>
            <span className="flex items-center gap-2 font-bold">{p.label}
              {p.needs ? <Badge>Key in MeetStream</Badge> : <Badge tone="green">Ready</Badge>}</span>
            <span className="mt-0.5 block text-xs text-ink-600">{p.note}</span>
          </button>
        ))}
      </div>
      <Field label="Voice">
        <Select className="w-56" disabled={!canEdit} value={pick.voice} onChange={(e) => { setPick({ ...pick, voice: e.target.value }); setResult(null) }}>
          {preset.voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
        </Select>
      </Field>
      {preset.needs && (
        <p className="text-xs text-ink-600">MeetStream runs the voice with your own {preset.needs} {/,| and /.test(preset.needs) ? 'keys' : 'key'}: add {/,| and /.test(preset.needs) ? 'them' : 'it'} at{' '}
          <a href={data.data.integrations_url} target="_blank" rel="noreferrer" className="font-bold underline decoration-2 underline-offset-2 hover:bg-accent-soft">
            app.meetstream.ai <ExternalLink className="inline h-3 w-3" /></a> under <b>Configure → Integrations</b>, then check.</p>
      )}
      {canEdit && <div className="flex flex-wrap gap-2">
        <Button size="sm" loading={busy === 'save'} disabled={!dirty} onClick={() => run('save')}>Save</Button>
        <Button size="sm" variant="secondary" loading={busy === 'check'} onClick={() => run('check')}>Check with MeetStream</Button>
      </div>}
      {result && (result.ok
        ? <p className="flex items-center gap-1.5 text-sm font-medium"><Check className="h-4 w-4" />{result.text}</p>
        : <ErrorBox error={result.text} />)}
    </div>
  )
}
