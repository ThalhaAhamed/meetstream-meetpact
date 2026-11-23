import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Card, ItemStatus, relTime } from '../components/ui'
import CommandMenu from '../components/CommandMenu'
import { api } from '../api'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('ui kit', () => {
  it('Card keeps a caller-supplied background instead of forcing white', () => {
    const { container } = render(<Card className="bg-pop-red">x</Card>)
    expect(container.firstChild.className).toContain('bg-pop-red')
    expect(container.firstChild.className).not.toContain('bg-white')
  })

  it('shows human status labels', () => {
    render(<ItemStatus status="in_progress" />)
    expect(screen.getByText('In progress')).toBeTruthy()
  })

  it('formats relative times both ways', () => {
    expect(relTime(new Date(Date.now() - 2 * 3600e3).toISOString())).toBe('2 hours ago')
    expect(relTime(new Date(Date.now() + 3 * 864e5 + 5000).toISOString())).toBe('in 3 days')
  })
})

describe('api client', () => {
  it('turns FastAPI error details into a readable message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Sign in first.' }), { status: 401 }))
    await expect(api.dashboard()).rejects.toThrow('Sign in first.')
  })
})

describe('command menu', () => {
  it('filters pages as you type and offers to ask', () => {
    vi.spyOn(api, 'directory').mockResolvedValue([])
    vi.spyOn(api, 'search').mockResolvedValue({ meetings: [], work_items: [], updates: [], transcript: [] })
    const Icon = () => null
    const nav = [['/', 'Team overview', Icon], ['/board', 'Work board', Icon], ['/reports', 'Reports', Icon]]
    render(<MemoryRouter><CommandMenu open onClose={() => {}} nav={nav} /></MemoryRouter>)
    fireEvent.change(screen.getByPlaceholderText(/Search people/), { target: { value: 'board' } })
    expect(screen.getByText('Work board')).toBeTruthy()
    expect(screen.queryByText('Reports')).toBeNull()
    expect(screen.getByText('Ask: "board"')).toBeTruthy()
  })
})
