import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Place } from '../../src/api/types'
import { PlaceField } from '../../src/panel/PlaceField'

const DENVER: Place = { label: 'Denver, CO', lat: 39.7392, lon: -104.9903, tz: 'America/Denver' }
const DENTON: Place = { label: 'Denton, TX', lat: 33.2148, lon: -97.1331, tz: 'America/Chicago' }

function stubPlaces(results: Place[] | 'error') {
  const fetchMock = vi.fn<(url: string) => Promise<Response>>(async () =>
    results === 'error'
      ? new Response(JSON.stringify({ error: { code: 'PROVIDER_UNAVAILABLE', message: 'down' } }), {
          status: 503,
        })
      : new Response(JSON.stringify(results), { status: 200 }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function Harness({ onChange }: { onChange?: (p: Place | null) => void }) {
  const [value, setValue] = useState<Place | null>(null)
  return (
    <PlaceField
      label="Origin"
      value={value}
      onChange={(place) => {
        setValue(place)
        onChange?.(place)
      }}
    />
  )
}

function renderField(onChange?: (p: Place | null) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Harness onChange={onChange} />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('PlaceField', () => {
  it('does not search for fewer than 3 characters', async () => {
    const fetchMock = stubPlaces([DENVER])
    renderField()
    await userEvent.type(screen.getByRole('combobox', { name: 'Origin' }), 'De')
    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('waits for a pause in typing and sends one request', async () => {
    const fetchMock = stubPlaces([DENVER, DENTON])
    renderField()
    await userEvent.type(screen.getByRole('combobox', { name: 'Origin' }), 'Denv')
    expect(fetchMock).not.toHaveBeenCalled() // still inside the 250 ms pause
    expect(await screen.findByRole('option', { name: 'Denver, CO' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/places?q=Denv')
  })

  it('chooses a place with the mouse', async () => {
    stubPlaces([DENVER, DENTON])
    const onChange = vi.fn()
    renderField(onChange)
    const input = screen.getByRole('combobox', { name: 'Origin' })
    await userEvent.type(input, 'Den')
    await userEvent.click(await screen.findByRole('option', { name: 'Denton, TX' }))

    expect(onChange).toHaveBeenLastCalledWith(DENTON)
    expect(input).toHaveValue('Denton, TX')
    expect(screen.queryByRole('option')).not.toBeInTheDocument()
  })

  it('works from the keyboard: arrows, Enter and Escape', async () => {
    stubPlaces([DENVER, DENTON])
    const onChange = vi.fn()
    renderField(onChange)
    const input = screen.getByRole('combobox', { name: 'Origin' })
    await userEvent.type(input, 'Den')
    await screen.findByRole('option', { name: 'Denver, CO' })

    await userEvent.keyboard('{ArrowDown}{ArrowDown}')
    expect(input).toHaveAttribute('aria-activedescendant', expect.stringMatching(/opt-1$/))
    await userEvent.keyboard('{Enter}')
    expect(onChange).toHaveBeenLastCalledWith(DENTON)

    await userEvent.clear(input)
    await userEvent.type(input, 'Den')
    await screen.findByRole('option', { name: 'Denver, CO' })
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('option')).not.toBeInTheDocument())
  })

  it('un-chooses the place as soon as the text is edited', async () => {
    stubPlaces([DENVER])
    const onChange = vi.fn()
    renderField(onChange)
    const input = screen.getByRole('combobox', { name: 'Origin' })
    await userEvent.type(input, 'Den')
    await userEvent.click(await screen.findByRole('option', { name: 'Denver, CO' }))
    await userEvent.type(input, 'x')
    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('says so when nothing matches', async () => {
    stubPlaces([])
    renderField()
    await userEvent.type(screen.getByRole('combobox', { name: 'Origin' }), 'Zzzz')
    expect(await screen.findByText(/no matches/i)).toBeInTheDocument()
  })

  it('says when suggestions could not be loaded instead of staying silent', async () => {
    stubPlaces('error')
    renderField()
    await userEvent.type(screen.getByRole('combobox', { name: 'Origin' }), 'Denv')
    // The lookup is retried once before it counts as failed.
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('down'), {
      timeout: 4000,
    })
    expect(screen.getByRole('status')).toHaveClass('text-severe')
  })

  it('shows a field error with role alert', () => {
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <PlaceField label="Origin" value={null} onChange={() => {}} error="Choose an origin." />
      </QueryClientProvider>,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Choose an origin.')
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-invalid', 'true')
  })
})
