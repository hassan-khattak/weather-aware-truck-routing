import { describe, expect, it } from 'vitest'
import type { Route } from '../../src/api/types'
import { truckAt } from '../../src/map/truck'
import { LINE_A, makeRoute } from '../fixtures'

const line = LINE_A.map(([lat, lon]) => [lon, lat] as [number, number])

/** 100 mi: drive 2 h to mile 100... with a 1 h rest at mile 50 (flat in the timeline). */
function route(over: Partial<Route> = {}): Route {
  return makeRoute('A', LINE_A, {
    distance_mi: 100,
    drive_s: 7200,
    total_s: 10800,
    stops: [{ type: 'rest', mile: 50, start_utc: '2026-11-24T22:00:00Z', duration_s: 3600 }],
    timeline: [
      [0, 0],
      [3600, 50],
      [7200, 50],
      [10800, 100],
    ],
    ...over,
  })
}

describe('truckAt', () => {
  it('starts at the origin', () => {
    const t = truckAt(route(), line, 0)
    expect(t.state).toBe('driving')
    expect(t.mile).toBe(0)
    expect(t.position).toEqual(line[0])
  })

  it('moves in proportion to elapsed time', () => {
    expect(truckAt(route(), line, 1800).mile).toBeCloseTo(25)
    expect(truckAt(route(), line, 9000).mile).toBeCloseTo(75)
  })

  it('stays put while parked at a stop', () => {
    const early = truckAt(route(), line, 4000)
    const late = truckAt(route(), line, 7000)
    expect(early.state).toBe('parked')
    expect(late.state).toBe('parked')
    expect(early.mile).toBe(50)
    expect(late.position).toEqual(early.position)
  })

  it('has arrived once the trip is over', () => {
    const t = truckAt(route(), line, 20000)
    expect(t.state).toBe('arrived')
    expect(t.mile).toBe(100)
    expect(t.position).toEqual(line[line.length - 1])
  })

  it('says the trip continues beyond a window shorter than the trip (trap T10)', () => {
    const long = route({
      distance_mi: 3000,
      total_s: 60 * 3600,
      timeline: [
        [0, 0],
        [60 * 3600, 3000],
      ],
      stops: [],
    })
    expect(truckAt(long, line, 48 * 3600, 48 * 3600).state).toBe('beyond-window')
    expect(truckAt(long, line, 10 * 3600, 48 * 3600).state).toBe('driving')
  })
})
