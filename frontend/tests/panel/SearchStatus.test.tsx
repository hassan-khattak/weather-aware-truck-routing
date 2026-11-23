import type { UseQueryResult } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'
import type { RiskResponse, RoutesResponse } from '../../src/api/types'
import { SearchStatus } from '../../src/panel/SearchStatus'
import { TripSummary } from '../../src/panel/TripSummary'
import { makeRisk, makeRoutes } from '../fixtures'

function result<T>(over: Record<string, unknown>): UseQueryResult<T, unknown> {
  const error = over.error ?? null
  return {
    isPending: false,
    isError: error !== null, // like a real query: an error result is an error
    data: undefined,
    error,
    refetch: vi.fn(),
    ...over,
  } as never
}
const routesPending = () => result<RoutesResponse>({ isPending: true })
const routesDone = () => result<RoutesResponse>({ data: makeRoutes() })
const riskPending = () => result<RiskResponse>({ isPending: true })
const riskDone = (data = makeRisk()) => result<RiskResponse>({ data })

describe('progress steps', () => {
  it('shows nothing before a search', () => {
    const { container } = render(
      <SearchStatus searched={false} routes={routesPending()} risk={riskPending()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the first step in progress while routes load', () => {
    render(<SearchStatus searched routes={routesPending()} risk={riskPending()} />)
    const steps = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(steps).toEqual(['●Finding truck routes…', '○Checking weather…', '○Scoring risk'])
  })

  it('shows the real checkpoint count once the routes are known', () => {
    render(<SearchStatus searched routes={routesDone()} risk={riskPending()} />)
    const steps = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(steps).toEqual([
      '✓Finding truck routes…',
      '●Checking weather at 24 checkpoints…', // two 100+ mile routes at 10 mi
      '○Scoring risk',
    ])
  })

  it('announces progress politely to screen readers', () => {
    render(<SearchStatus searched routes={routesPending()} risk={riskPending()} />)
    expect(screen.getByRole('list')).toHaveAttribute('aria-live', 'polite')
  })

  it('disappears when the search has finished', () => {
    render(<SearchStatus searched routes={routesDone()} risk={riskDone()} />)
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })
})

describe('problems', () => {
  it('explains a routes failure in plain language without a retry for user mistakes', () => {
    const routes = result<RoutesResponse>({
      error: new ApiError(
        422,
        'NO_ROUTE',
        'No truck route found between these places. Try a nearby city.',
      ),
    })
    render(<SearchStatus searched routes={routes} risk={riskPending()} />)
    expect(screen.getByRole('alert')).toHaveTextContent(
      'No truck route found between these places.',
    )
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument() // no spinner after a failure
  })

  it('offers Try again for an outage and retries the routes request', async () => {
    const routes = result<RoutesResponse>({
      error: new ApiError(
        503,
        'PROVIDER_UNAVAILABLE',
        'Weather/route data is temporarily unavailable, try again in a minute.',
      ),
    })
    render(<SearchStatus searched routes={routes} risk={riskPending()} />)
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(routes.refetch).toHaveBeenCalledTimes(1)
  })

  it('keeps the routes but says risk is unknown when only the weather step fails', async () => {
    const risk = result<RiskResponse>({
      error: new ApiError(429, 'RATE_LIMITED', 'Too many searches; please wait a few minutes.'),
    })
    render(<SearchStatus searched routes={routesDone()} risk={risk} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Too many searches; please wait a few minutes.')
    expect(alert).toHaveTextContent('weather risk is unknown') // never shown as safe
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(risk.refetch).toHaveBeenCalledTimes(1)
  })
})

describe('stale weather', () => {
  const now = () => Date.parse('2026-11-24T20:00:00Z')

  it('labels old weather with its age', () => {
    const stale = { ...makeRisk(), stale: true, weather_as_of: '2026-11-24T18:00:00Z' }
    render(<SearchStatus searched routes={routesDone()} risk={riskDone(stale)} now={now} />)
    expect(screen.getByRole('status')).toHaveTextContent(
      'Weather as of 2 h ago. Live data temporarily unavailable.',
    )
  })

  it('says nothing about fresh weather', () => {
    render(<SearchStatus searched routes={routesDone()} risk={riskDone()} now={now} />)
    expect(screen.queryByText(/weather as of/i)).not.toBeInTheDocument()
  })
})

describe('TripSummary', () => {
  const request = {
    origin: { label: 'Dallas, TX', lat: 32.78, lon: -96.8 },
    destination: { label: 'Denver, CO', lat: 39.74, lon: -104.99 },
    departure_local: '2026-11-24T15:00',
    load_lb: 42000,
  }

  it('is one line with the cities, the departure in the origin zone and the load', () => {
    render(<TripSummary request={request} tz="America/Chicago" onEdit={() => {}} />)
    expect(screen.getByText('Dallas → Denver · Tue 3 PM CST · 42,000 lb')).toBeInTheDocument()
  })

  it('reopens the form with the pencil button', async () => {
    const onEdit = vi.fn()
    render(<TripSummary request={request} tz="America/Chicago" onEdit={onEdit} />)
    await userEvent.click(screen.getByRole('button', { name: 'Edit trip' }))
    expect(onEdit).toHaveBeenCalled()
  })
})
