import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Users } from 'lucide-react'
import { api } from '../api'
import { Avatar, Badge, Card, Empty, ErrorBox, Input, PageHeader, Spinner, useLoad } from '../components/ui'

export default function People() {
  const { data, error, loading } = useLoad(() => api.employees(), [])
  const [q, setQ] = useState('')
  const rows = (data || []).filter((e) => e.active && (e.name + ' ' + e.title + ' ' + (e.team_name || '')).toLowerCase().includes(q.toLowerCase()))
  const byTeam = rows.reduce((acc, e) => { (acc[e.team_name || 'No team'] ||= []).push(e); return acc }, {})

  return (
    <>
      <PageHeader title="People" subtitle="Each person's record is built from what they report in meetings"
        actions={<div className="relative"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-ink-400" /><Input className="w-56 pl-8" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} /></div>} />
      <ErrorBox error={error} />
      {loading && !data ? <Spinner /> : !rows.length ? <Card><Empty icon={Users} title="No people">Managers add employees under Admin.</Empty></Card> : (
        <div className="space-y-6">
          {Object.entries(byTeam).map(([team, list]) => (
            <div key={team}>
              <h2 className="mb-2 text-xs font-semibold text-ink-400">{team}</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {list.map((e) => (
                  <Link key={e.id} to={`/people/${e.id}`}>
                    <Card className="flex items-center gap-3 p-4 transition-shadow duration-200 hover:shadow-lift">
                      <Avatar name={e.name} size={10} />
                      <div className="min-w-0">
                        <p className="truncate font-medium">{e.name}</p>
                        <p className="truncate text-xs text-ink-500">{e.title || e.email}</p>
                        {e.aliases.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{e.aliases.slice(0, 2).map((a) => <Badge key={a}>{a}</Badge>)}</div>}
                      </div>
                    </Card>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
