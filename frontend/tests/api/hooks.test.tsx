import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../src/api/client'
import { shouldRetry, useTrip, usePlaces } from '../../src/api/hooks'
import type { RoutesRequest } from '../../src/api/types'

const REQUEST: RoutesRequest = {
  origin: { label: 'Denver, CO', lat: 39.74, lon: -104.99 },
  destination: { label: 'Cheyenne, WY', lat: 41.14, lon: -104.82 },
  departure_local: '2026-11-24T14:00',
  load_lb: 42000,
}

const ok = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
const fail = (status: number, code: string) =>
  new Response(JSON.stringify({ error: { code, message: `${code} message` } }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

/** Routes the fetch mock by URL so call order does not matter. */
function stubApi(handlers: Record<string, (() => Response)[]>) {
  const queues = Object.fromEntries(Object.entries(handlers).map(([k, v]) => [k, [...v]]))
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      calls.push(url)
      const queue = queues[url]
      const next = queue.length > 1 ? queue.shift()! : queue[0]
      return next()
    }),
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('usePlaces', () => {
  it('does not call the server for fewer than 3 characters', async () => {
    const calls = stubApi({})
    renderHook(() => usePlaces('de'), { wrapper: wrapper() })
    await new Promise((r) => setTimeout(r, 20))
    expect(calls).toEqual([])
  })

  it('fetches suggestions from 3 characters', async () => {
    const calls = stubApi({ '/api/v1/places?q=Den': [() => ok([{ label: 'Denver, CO' }])] })
    const { result } = renderHook(() => usePlaces(' Den '), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.data).toHaveLength(1))
    expect(calls).toEqual(['/api/v1/places?q=Den'])
  })
})

describe('useTrip', () => {
  it('does nothing until a search is submitted', async () => {
    const calls = stubApi({})
    renderHook(() => useTrip(null, 0), { wrapper: wrapper() })
    await new Promise((r) => setTimeout(r, 20))
    expect(calls).toEqual([])
  })

  it('fetches routes first, then risk for the returned trip', async () => {
    const calls = stubApi({
      '/api/v1/routes': [() => ok({ trip_id: 't_1', routes: [] })],
      '/api/v1/risk': [() => ok({ routes: [], stale: false })],
    })
    const { result } = renderHook(() => useTrip(REQUEST, 1), { wrapper: wrapper() })

    await waitFor(() => expect(result.current.routes.data?.trip_id).toBe('t_1'))
    await waitFor(() => expect(result.current.risk.data).toBeDefined())
    expect(calls).toEqual(['/api/v1/routes', '/api/v1/risk'])
  })

  it('does not ask for risk when routes fail', async () => {
    const calls = stubApi({ '/api/v1/routes': [() => fail(422, 'NO_ROUTE')] })
    const { result } = renderHook(() => useTrip(REQUEST, 1), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.routes.error).toBeInstanceOf(ApiError))
    expect(result.current.risk.fetchStatus).toBe('idle')
    expect(calls).toEqual(['/api/v1/routes']) // not retried: the user must change the input
  })

  it('silently searches again when the stored trip has expired', async () => {
    const calls = stubApi({
      '/api/v1/routes': [
        () => ok({ trip_id: 't_old', routes: [] }),
        () => ok({ trip_id: 't_new', routes: [] }),
      ],
      '/api/v1/risk': [() => fail(410, 'TRIP_EXPIRED'), () => ok({ routes: [], stale: false })],
    })
    const { result } = renderHook(() => useTrip(REQUEST, 1), { wrapper: wrapper() })

    await waitFor(() => expect(result.current.risk.data).toBeDefined())
    expect(result.current.risk.error).toBeNull()
    expect(calls).toEqual(['/api/v1/routes', '/api/v1/risk', '/api/v1/routes', '/api/v1/risk'])
    expect(result.current.routes.data?.trip_id).toBe('t_new') // the cache now holds the fresh trip
  })

  it('shows other risk errors instead of hiding them', async () => {
    stubApi({
      '/api/v1/routes': [() => ok({ trip_id: 't_1', routes: [] })],
      '/api/v1/risk': [() => fail(429, 'RATE_LIMITED')],
    })
    const { result } = renderHook(() => useTrip(REQUEST, 1), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.risk.error).toBeInstanceOf(ApiError))
    expect((result.current.risk.error as ApiError).code).toBe('RATE_LIMITED')
  })

  it('retries a provider outage once', async () => {
    const calls = stubApi({
      '/api/v1/routes': [
        () => fail(503, 'PROVIDER_UNAVAILABLE'),
        () => ok({ trip_id: 't_1', routes: [] }),
      ],
      '/api/v1/risk': [() => ok({ routes: [] })],
    })
    const { result } = renderHook(() => useTrip(REQUEST, 1), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.routes.data?.trip_id).toBe('t_1'))
    expect(calls.filter((c) => c === '/api/v1/routes')).toHaveLength(2)
  })
})

describe('searchId', () => {
  it('searching again with the same input fetches afresh', async () => {
    const calls = stubApi({
      '/api/v1/routes': [() => ok({ trip_id: 't_1', routes: [] })],
      '/api/v1/risk': [() => ok({ routes: [] })],
    })
    const { result, rerender } = renderHook(({ id }) => useTrip(REQUEST, id), {
      wrapper: wrapper(),
      initialProps: { id: 1 },
    })
    await waitFor(() => expect(result.current.risk.data).toBeDefined())
    rerender({ id: 1 })
    expect(calls).toHaveLength(2) // same search: served from cache

    rerender({ id: 2 })
    await waitFor(() => expect(calls).toHaveLength(4)) // explicit new search: routes + risk again
  })
})

describe('shouldRetry', () => {
  it('retries network and provider outages once, nothing else', () => {
    expect(shouldRetry(0, new ApiError(0, 'NETWORK', 'x'))).toBe(true)
    expect(shouldRetry(0, new ApiError(503, 'PROVIDER_UNAVAILABLE', 'x'))).toBe(true)
    expect(shouldRetry(1, new ApiError(503, 'PROVIDER_UNAVAILABLE', 'x'))).toBe(false)
    expect(shouldRetry(0, new ApiError(422, 'NO_ROUTE', 'x'))).toBe(false)
    expect(shouldRetry(0, new ApiError(429, 'RATE_LIMITED', 'x'))).toBe(false)
    expect(shouldRetry(0, new Error('boom'))).toBe(false)
  })
})
