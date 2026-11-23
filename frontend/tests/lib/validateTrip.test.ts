import { DateTime } from 'luxon'
import { describe, expect, it } from 'vitest'
import type { Place } from '../../src/api/types'
import { validateTrip, type TripInput } from '../../src/lib/validateTrip'

const NOW = DateTime.fromISO('2026-11-24T18:00:00Z', { zone: 'utc' }) // 12:00 in Chicago
const DALLAS: Place = { label: 'Dallas, TX', lat: 32.7767, lon: -96.797, tz: 'America/Chicago' }
const DENVER: Place = { label: 'Denver, CO', lat: 39.7392, lon: -104.9903, tz: 'America/Denver' }
const TORONTO: Place = { label: 'Toronto, ON', lat: 43.65, lon: -79.38, tz: null }

const base: TripInput = {
  origin: DALLAS,
  destination: DENVER,
  departure: '2026-11-24T15:00',
  load: '42000',
}
const check = (over: Partial<TripInput> = {}) => validateTrip({ ...base, ...over }, NOW)

describe('a valid trip', () => {
  it('produces the API request without extra fields on the places', () => {
    const result = check()
    expect(result.errors).toEqual({})
    expect(result.request).toEqual({
      origin: { label: 'Dallas, TX', lat: 32.7767, lon: -96.797 },
      destination: { label: 'Denver, CO', lat: 39.7392, lon: -104.9903 },
      departure_local: '2026-11-24T15:00',
      load_lb: 42000,
    })
    expect(result.warning).toBeUndefined()
  })
})

describe('places', () => {
  it('needs both places chosen from the suggestions', () => {
    const result = check({ origin: null, destination: null })
    expect(result.errors.origin).toBe('Choose an origin from the suggestions.')
    expect(result.errors.destination).toBe('Choose a destination from the suggestions.')
    expect(result.request).toBeUndefined()
  })

  it('rejects places outside the continental US', () => {
    const coverage = 'Currently supports routes within the continental US.'
    expect(check({ origin: TORONTO }).errors.origin).toBe(coverage)
    expect(check({ destination: TORONTO }).errors.destination).toBe(coverage)
  })

  it('rejects the same place twice, including places under half a mile apart', () => {
    const message = 'Choose a destination different from the origin.'
    expect(check({ destination: DALLAS }).errors.destination).toBe(message)
    expect(check({ destination: { ...DALLAS, lat: DALLAS.lat + 0.002 } }).errors.destination).toBe(
      message,
    )
    expect(
      check({ destination: { ...DALLAS, lat: DALLAS.lat + 0.02 } }).errors.destination,
    ).toBeUndefined()
  })
})

describe('departure (origin local time, window now-5min .. now+48h)', () => {
  it('rejects the past but allows 5 minutes of grace', () => {
    // 12:00 CST is "now". 11:55 is exactly 5 minutes ago.
    expect(check({ departure: '2026-11-24T11:55' }).errors.departure).toBeUndefined()
    expect(check({ departure: '2026-11-24T11:54' }).errors.departure).toBe(
      "Departure can't be in the past.",
    )
  })

  it('allows exactly 48 hours ahead and rejects later', () => {
    expect(check({ departure: '2026-11-26T12:00' }).errors.departure).toBeUndefined()
    expect(check({ departure: '2026-11-26T12:01' }).errors.departure).toBe(
      'Departure must be within the next 48 hours.',
    )
  })

  it('is read in the origin zone, not the browser zone', () => {
    // 11:30 is the past in Chicago (12:00 now) but would be the future in Los Angeles.
    const la: Place = { ...DALLAS, tz: 'America/Los_Angeles' }
    expect(check({ departure: '2026-11-24T11:30' }).errors.departure).toBe(
      "Departure can't be in the past.",
    )
    expect(check({ origin: la, departure: '2026-11-24T11:30' }).errors.departure).toBeUndefined()
  })

  it('needs a valid time', () => {
    expect(check({ departure: '' }).errors.departure).toBe('Choose a departure time.')
    expect(check({ departure: 'soon' }).errors.departure).toBe(
      'Departure must look like 2026-11-24T15:00.',
    )
  })
})

describe('load', () => {
  it.each(['1000', '45000', '80000'])('accepts %s lb', (load) => {
    expect(check({ load }).errors.load).toBeUndefined()
  })

  it.each(['999', '80001', '0', '-5'])(
    'rejects %s lb with the same words as the server',
    (load) => {
      expect(check({ load }).errors.load).toBe('Load must be between 1,000 and 80,000 lb.')
    },
  )

  it.each(['', '  ', 'heavy'])('rejects %j as not a number', (load) => {
    expect(check({ load }).errors.load).toBe('Enter the cargo weight in pounds.')
  })

  it('warns above 45,000 lb without blocking the search', () => {
    const heavy = check({ load: '45001' })
    expect(heavy.warning).toMatch(/exceeds typical legal cargo/i)
    expect(heavy.request).toBeDefined()
    expect(check({ load: '45000' }).warning).toBeUndefined()
  })
})
