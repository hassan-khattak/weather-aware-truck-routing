import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, fetchPlaces, friendlyMessage, postRisk, postRoutes } from '../../src/api/client'
import type { RoutesRequest } from '../../src/api/types'

const REQUEST: RoutesRequest = {
  origin: { label: 'Dallas, TX', lat: 32.78, lon: -96.8 },
  destination: { label: 'Denver, CO', lat: 39.74, lon: -104.99 },
  departure_local: '2026-11-24T15:00',
  load_lb: 42000,
}

function respond(status: number, body: unknown, asText = false): Response {
  return new Response(asText ? String(body) : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': asText ? 'text/html' : 'application/json' },
  })
}

function stubFetch(...responses: (Response | Error | DOMException)[]) {
  const fetchMock = vi.fn()
  for (const r of responses) {
    if (r instanceof Response) fetchMock.mockResolvedValueOnce(r)
    else fetchMock.mockRejectedValueOnce(r)
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('requests', () => {
  it('asks for places with an encoded query', async () => {
    const fetchMock = stubFetch(respond(200, [{ label: 'Denver, CO', lat: 1, lon: 2, tz: null }]))
    const places = await fetchPlaces('St. Louis, MO')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/places?q=St.%20Louis%2C%20MO')
    expect(places[0].label).toBe('Denver, CO')
  })

  it('posts the routes request as JSON', async () => {
    const fetchMock = stubFetch(respond(200, { trip_id: 't_1', routes: [] }))
    await postRoutes(REQUEST)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/routes')
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual(REQUEST)
  })

  it('posts only the trip id for risk', async () => {
    const fetchMock = stubFetch(respond(200, { routes: [] }))
    await postRisk('t_abc')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/risk')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ trip_id: 't_abc' })
  })
})

describe('errors', () => {
  it.each([
    [400, 'VALIDATION_ERROR', 'Load must be between 1,000 and 80,000 lb.'],
    [422, 'OUT_OF_COVERAGE', 'Currently supports routes within the continental US.'],
    [422, 'NO_ROUTE', 'No truck route found between these places. Try a nearby city.'],
    [
      503,
      'PROVIDER_UNAVAILABLE',
      'Weather/route data is temporarily unavailable, try again in a minute.',
    ],
    [429, 'RATE_LIMITED', 'Too many searches; please wait a few minutes.'],
    [410, 'TRIP_EXPIRED', 'This trip has expired. Searching again.'],
  ])('maps %i %s to an ApiError carrying the server message', async (status, code, message) => {
    stubFetch(respond(status, { error: { code, message, fields: { load_lb: message } } }))
    const error = await postRoutes(REQUEST).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status, code, message, fields: { load_lb: message } })
    expect(friendlyMessage(error)).toBe(message)
  })

  it('turns a failed connection into a friendly network error', async () => {
    stubFetch(new TypeError('Failed to fetch'))
    const error = await postRoutes(REQUEST).catch((e: unknown) => e)
    expect(error).toMatchObject({ code: 'NETWORK', status: 0 })
    expect(friendlyMessage(error)).toMatch(/can't reach the server/i)
  })

  it('does not hide an aborted request as an error message', async () => {
    stubFetch(new DOMException('aborted', 'AbortError'))
    const error = await fetchPlaces('Den').catch((e: unknown) => e)
    expect(error).toMatchObject({ name: 'AbortError' })
  })

  it('copes with a non-JSON error page from a proxy', async () => {
    stubFetch(respond(502, '<html>Bad gateway</html>', true))
    const error = await postRoutes(REQUEST).catch((e: unknown) => e)
    expect(error).toMatchObject({ status: 502, code: 'HTTP_502' })
    expect(friendlyMessage(error)).toMatch(/something went wrong/i)
  })

  it('copes with a successful response that is not JSON', async () => {
    stubFetch(respond(200, 'nope', true))
    const error = await postRisk('t_1').catch((e: unknown) => e)
    expect(error).toMatchObject({ code: 'BAD_RESPONSE' })
  })

  it('gives unknown errors a generic message', () => {
    expect(friendlyMessage(new Error('boom'))).toMatch(/something went wrong/i)
  })
})
