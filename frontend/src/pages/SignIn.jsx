import { useState } from 'react'
import { api } from '../api'
import { Button, Card, ErrorBox, Field, Input } from '../components/ui'

export default function SignIn({ needsSetup, onSignedIn }) {
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const user = needsSetup ? await api.setup(form) : await api.login({ email: form.email, password: form.password })
      onSignedIn(user)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-50 p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2.5">
          <img src="/logo-mark.svg" alt="" className="h-11 w-11" />
          <div>
            <p className="text-lg font-bold">MeetPact</p>
            <p className="text-xs text-ink-500">AI meeting notes and progress, built on MeetStream</p>
          </div>
        </div>
        <Card className="p-6">
          <h1 className="text-lg font-semibold">{needsSetup ? 'Create the admin account' : 'Sign in'}</h1>
          <p className="mb-5 mt-1 text-sm text-ink-500">
            {needsSetup ? 'This is a fresh install. The first account becomes the admin.' : 'Use the account your admin created for you.'}
          </p>
          <form onSubmit={submit} className="space-y-3.5">
            {needsSetup && <Field label="Your name"><Input value={form.name} onChange={set('name')} required autoFocus /></Field>}
            <Field label="Email"><Input type="email" value={form.email} onChange={set('email')} required autoFocus={!needsSetup} /></Field>
            <Field label="Password" hint={needsSetup ? 'At least 8 characters.' : undefined}>
              <Input type="password" value={form.password} onChange={set('password')} required minLength={needsSetup ? 8 : undefined} />
            </Field>
            <ErrorBox error={error} />
            <Button type="submit" loading={busy} className="w-full">{needsSetup ? 'Create account' : 'Sign in'}</Button>
          </form>
        </Card>
      </div>
    </div>
  )
}
