import { describe, expect, it } from 'vitest'
import { ApiError } from '../../src/api/client'
import { relativeAge } from '../../src/lib/age'
import { checkpointCount, totalCheckpoints } from '../../src/lib/checkpoints'
import { isRetryable, serverFieldErrors } from '../../src/lib/serverErrors'
import { makeRoute } from '../fixtures'

describe('checkpointCount (mirrors the backend rule)', () => {
  // Counts taken from the backend's golden scenario and a sample trip.
  it.each([
    [1071.3, 50, 23], // Chicago -> Dallas, route A
    [1049.7, 50, 22], // route B
    [1171.3, 50, 25], // route C
    [108.5, 10, 12], // Denver -> Cheyenne: 0, 10 ... 100, destination
    [8, 25, 2], // shorter than the interval: origin and destination
    [0.4, 25, 2],
  ])('%f mi every %i mi has %i checkpoints', (miles, interval, count) => {
    expect(checkpointCount(miles, interval)).toBe(count)
  })

  it('merges a final gap under one mile into the destination', () => {
    // Regular checkpoints at 0, 25, 50; destination at 50.5 replaces the one at 50.
    expect(checkpointCount(50.5, 25)).toBe(3)
    expect(checkpointCount(51.5, 25)).toBe(4)
  })

  it('adds up all routes', () => {
    const routes = [
      makeRoute('A', [], { distance_mi: 108.5 }),
      makeRoute('B', [], { distance_mi: 106.5 }),
    ]
    expect(totalCheckpoints(routes, 10)).toBe(12 + 12)
  })
})

describe('relativeAge', () => {
  const now = Date.parse('2026-11-24T18:00:00Z')
  it.each([
    ['2026-11-24T18:00:00Z', 'just now'],
    ['2026-11-24T17:15:00Z', '45 min ago'],
    ['2026-11-24T16:00:00Z', '2 h ago'],
    ['2026-11-21T18:00:00Z', '3 days ago'],
    ['2026-11-24T19:00:00Z', 'just now'], // a future time never reads as negative
  ])('%s is %s', (iso, text) => {
    expect(relativeAge(iso, now)).toBe(text)
  })
})

describe('serverFieldErrors', () => {
  it('maps API field paths onto the form fields', () => {
    const error = new ApiError(400, 'VALIDATION_ERROR', 'x', {
      'origin.lat': 'Bad latitude.',
      destination: 'Choose a destination different from the origin.',
      departure_local: "Departure can't be in the past.",
      load_lb: 'Load must be between 1,000 and 80,000 lb.',
      something_else: 'ignored',
    })
    expect(serverFieldErrors(error)).toEqual({
      origin: 'Bad latitude.',
      destination: 'Choose a destination different from the origin.',
      departure: "Departure can't be in the past.",
      load: 'Load must be between 1,000 and 80,000 lb.',
    })
  })

  it('ignores other errors', () => {
    expect(serverFieldErrors(new ApiError(422, 'NO_ROUTE', 'x'))).toEqual({})
    expect(serverFieldErrors(new Error('boom'))).toEqual({})
    expect(serverFieldErrors(null)).toEqual({})
  })
})

describe('isRetryable', () => {
  it('offers retry only for problems that may pass', () => {
    for (const code of ['NETWORK', 'PROVIDER_UNAVAILABLE', 'RATE_LIMITED']) {
      expect(isRetryable(new ApiError(503, code, 'x'))).toBe(true)
    }
    for (const code of ['NO_ROUTE', 'OUT_OF_COVERAGE', 'VALIDATION_ERROR']) {
      expect(isRetryable(new ApiError(422, code, 'x'))).toBe(false)
    }
    expect(isRetryable(new Error('boom'))).toBe(false)
  })
})
