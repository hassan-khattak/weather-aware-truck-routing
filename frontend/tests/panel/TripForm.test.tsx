import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DateTime } from 'luxon'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Place, RoutesRequest } from '../../src/api/types'
import { TripForm } from '../../src/panel/TripForm'

const NOW = DateTime.fromISO('2026-11-24T18:00:00Z', { zone: 'utc' }) // 12:00 CST, 11:00 MST
const DALLAS: Place = { label: 'Dallas, TX', lat: 32.7767, lon: -96.797, tz: 'America/Chicago' }
const DENVER: Place = { label: 'Denver, CO', lat: 39.7392, lon: -104.9903, tz: 'America/Denver' }
const TORONTO: Place = { label: 'Toronto, ON', lat: 43.65, lon: -79.38, tz: null }
const INITIAL = { origin: DALLAS, destination: DENVER, departure: '2026-11-24T15:00', load: 42000 }

afterEach(() => vi.unstubAllGlobals())

function setup(props: Partial<Parameters<typeof TripForm>[0]> = {}) {
  vi.stubGlobal('fetch', vi.fn())
  const onSubmit = vi.fn<(request: RoutesRequest, originTz: string) => void>()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TripForm onSubmit={onSubmit} now={() => NOW} {...props} />
    </QueryClientProvider>,
  )
  return { onSubmit, user: userEvent.setup() }
}

const submitButton = () => screen.getByRole('button', { name: /find the safest route/i })

describe('departure field', () => {
  it('names the origin zone, and shows a neutral label before an origin is chosen', () => {
    setup()
    expect(screen.getByLabelText(/departure \(origin's local time\)/i)).toBeInTheDocument()
  })

  it('labels the zone once an origin is known', () => {
    setup({ initial: INITIAL })
    expect(screen.getByLabelText('Departure (CST · Chicago)')).toHaveValue('2026-11-24T15:00')
  })

  it('limits the picker to now .. +48 h in the origin zone', () => {
    setup({ initial: INITIAL })
    const input = screen.getByLabelText(/departure \(/i)
    expect(input).toHaveAttribute('min', '2026-11-24T11:55')
    expect(input).toHaveAttribute('max', '2026-11-26T12:00')
  })
})

describe('sample trips', () => {
  it('one click fills the form and searches with the next full hour at the origin', async () => {
    const { onSubmit, user } = setup()
    await user.click(screen.getByRole('button', { name: /chicago → dallas/i }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith(
      {
        origin: { label: 'Chicago, IL', lat: 41.8781, lon: -87.6298 },
        destination: { label: 'Dallas, TX', lat: 32.7767, lon: -96.797 },
        departure_local: '2026-11-24T13:00',
        load_lb: 42000,
      },
      'America/Chicago',
    )
    expect(screen.getByRole('combobox', { name: 'Origin' })).toHaveValue('Chicago, IL')
  })

  it('offers the four sample trips', () => {
    setup()
    const samples = within(screen.getByRole('region', { name: 'Sample trips' })).getAllByRole(
      'button',
    )
    expect(samples.map((b) => b.textContent)).toEqual([
      expect.stringContaining('Denver → Cheyenne'),
      expect.stringContaining('Salt Lake City → Denver'),
      expect.stringContaining('Chicago → Dallas'),
      expect.stringContaining('Seattle → Chicago'),
    ])
  })

  it('uses the origin zone for each sample (Seattle is Pacific)', async () => {
    const { onSubmit, user } = setup()
    await user.click(screen.getByRole('button', { name: /seattle → chicago/i }))
    expect(onSubmit.mock.calls[0][0].departure_local).toBe('2026-11-24T11:00') // 10:00 PST now
  })
})

describe('submitting', () => {
  it('sends the request for a valid form', async () => {
    const { onSubmit, user } = setup({ initial: INITIAL })
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledWith(
      {
        origin: { label: 'Dallas, TX', lat: 32.7767, lon: -96.797 },
        destination: { label: 'Denver, CO', lat: 39.7392, lon: -104.9903 },
        departure_local: '2026-11-24T15:00',
        load_lb: 42000,
      },
      'America/Chicago',
    )
  })

  it('explains what is missing and does not search', async () => {
    const { onSubmit, user } = setup()
    await user.click(submitButton())
    expect(onSubmit).not.toHaveBeenCalled()
    const alerts = screen.getAllByRole('alert').map((a) => a.textContent)
    expect(alerts).toContain('Choose an origin from the suggestions.')
    expect(alerts).toContain('Choose a destination from the suggestions.')
  })

  it('shows the same load message the server would', async () => {
    const { onSubmit, user } = setup({ initial: INITIAL })
    const load = screen.getByLabelText(/cargo weight/i)
    await user.clear(load)
    await user.type(load, '500')
    await user.click(submitButton())
    expect(screen.getByRole('alert')).toHaveTextContent('Load must be between 1,000 and 80,000 lb.')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('warns about a very heavy load but still searches', async () => {
    const { onSubmit, user } = setup({ initial: { ...INITIAL, load: 50000 } })
    expect(screen.getByRole('note')).toHaveTextContent(/exceeds typical legal cargo/i)
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('rejects a departure in the past', async () => {
    const { onSubmit, user } = setup({ initial: { ...INITIAL, departure: '2026-11-24T09:00' } })
    await user.click(submitButton())
    expect(screen.getByRole('alert')).toHaveTextContent("Departure can't be in the past.")
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('rejects a place outside the US', async () => {
    const { onSubmit, user } = setup({ initial: { ...INITIAL, destination: TORONTO } })
    await user.click(submitButton())
    expect(screen.getByRole('alert')).toHaveTextContent(/continental US/i)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('shows field errors that come back from the server', () => {
    setup({ initial: INITIAL, serverErrors: { load: 'Server says no.' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Server says no.')
  })
})

describe('swap', () => {
  it('swaps origin and destination and moves the departure to the new origin zone', async () => {
    const { user } = setup({ initial: { ...INITIAL, departure: '' } })
    expect(screen.getByRole('combobox', { name: 'Origin' })).toHaveValue('Dallas, TX')

    await user.click(screen.getByRole('button', { name: /swap origin and destination/i }))
    expect(screen.getByRole('combobox', { name: 'Origin' })).toHaveValue('Denver, CO')
    expect(screen.getByRole('combobox', { name: 'Destination' })).toHaveValue('Dallas, TX')
    // The new origin is in Denver (MST), 11:00 now, so the default is 12:00 there.
    const departure = screen.getByLabelText('Departure (MST · Denver)')
    expect(departure).toHaveValue('2026-11-24T12:00')
  })
})
