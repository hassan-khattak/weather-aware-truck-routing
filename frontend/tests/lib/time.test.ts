import { DateTime } from 'luxon'
import { describe, expect, it } from 'vitest'
import {
  departureWindow,
  nextFullHour,
  parseLocal,
  summaryTime,
  zoneLabel,
} from '../../src/lib/time'

const at = (iso: string) => DateTime.fromISO(iso, { zone: 'utc' })

describe('nextFullHour', () => {
  it('rounds up to the next hour in the origin zone', () => {
    expect(nextFullHour('America/Chicago', at('2026-11-24T18:37:00Z'))).toBe('2026-11-24T13:00')
    expect(nextFullHour('America/Los_Angeles', at('2026-11-24T18:37:00Z'))).toBe('2026-11-24T11:00')
  })

  it('moves on from an exact hour', () => {
    expect(nextFullHour('America/Chicago', at('2026-11-24T18:00:00Z'))).toBe('2026-11-24T13:00')
  })

  it('skips the hour that does not exist when clocks go forward', () => {
    // 01:30 CST on 2026-03-08; 02:00 does not exist, the next real hour is 03:00 CDT.
    expect(nextFullHour('America/Chicago', at('2026-03-08T07:30:00Z'))).toBe('2026-03-08T03:00')
  })

  it('rolls over midnight', () => {
    expect(nextFullHour('America/Denver', at('2026-11-25T06:20:00Z'))).toBe('2026-11-25T00:00')
  })
})

describe('zoneLabel', () => {
  it.each([
    ['America/Chicago', '2026-11-24T18:00:00Z', 'CST · Chicago'],
    ['America/Chicago', '2026-07-01T18:00:00Z', 'CDT · Chicago'],
    ['America/Phoenix', '2026-07-01T18:00:00Z', 'MST · Phoenix'],
    ['America/Los_Angeles', '2026-11-24T18:00:00Z', 'PST · Los Angeles'],
    ['America/Indiana/Indianapolis', '2026-11-24T18:00:00Z', 'EST · Indianapolis'],
  ])('%s at %s -> %s', (zone, iso, label) => {
    expect(zoneLabel(zone, at(iso))).toBe(label)
  })
})

describe('departureWindow', () => {
  it('allows 5 minutes in the past up to 48 hours ahead, in the origin zone', () => {
    expect(departureWindow('America/Chicago', at('2026-11-24T18:00:00Z'))).toEqual({
      min: '2026-11-24T11:55',
      max: '2026-11-26T12:00',
    })
  })
})

describe('parseLocal', () => {
  it('parses a wall-clock time in the given zone', () => {
    const parsed = parseLocal('2026-11-24T15:00', 'America/Chicago')
    expect(parsed?.toUTC().toISO()).toBe('2026-11-24T21:00:00.000Z')
  })

  it.each(['', 'tomorrow', '2026-02-30T10:00', '2026-11-24'])('rejects %j', (text) => {
    expect(parseLocal(text, 'America/Chicago')).toBeNull()
  })
})

describe('summaryTime', () => {
  it('formats a short summary with the zone abbreviation', () => {
    expect(summaryTime('2026-11-24T15:00', 'America/Chicago')).toBe('Tue 3 PM CST')
    expect(summaryTime('2026-11-24T15:30', 'America/Chicago')).toBe('Tue 3:30 PM CST')
  })

  it('falls back to the raw text for something unparseable', () => {
    expect(summaryTime('nonsense', 'America/Chicago')).toBe('nonsense')
  })
})
