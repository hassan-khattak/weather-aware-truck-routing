import { describe, expect, it } from 'vitest'
import type { Segment } from '../../src/api/types'
import { formatDuration, formatMiles } from '../../src/lib/format'
import { boundsOf } from '../../src/map/bounds'
import { buildGradient } from '../../src/map/gradient'
import { resolveSelectedId } from '../../src/state/selection'
import { LEVELS } from '../../src/levels'
import { makeRisk, makeRoutes } from '../fixtures'

describe('buildGradient', () => {
  const seg = (from_mi: number, to_mi: number, level: Segment['level']): Segment => ({
    from_mi,
    to_mi,
    level,
  })

  it('returns null without segments or distance', () => {
    expect(buildGradient([], 100)).toBeNull()
    expect(buildGradient([seg(0, 10, 'LOW')], 0)).toBeNull()
  })

  it('colours one segment with one colour from start to end', () => {
    const expression = buildGradient([seg(0, 100, 'HIGH')], 100)!
    expect(expression.slice(0, 3)).toEqual(['interpolate', ['linear'], ['line-progress']])
    expect(expression.slice(3)).toEqual([0, LEVELS.HIGH.color, 1, LEVELS.HIGH.color])
  })

  it('makes hard colour edges at the segment boundaries', () => {
    const expression = buildGradient([seg(0, 40, 'LOW'), seg(40, 100, 'SEVERE')], 100)!
    const stops = expression.slice(3) as (number | string)[]
    const pairs = [] as [number, string][]
    for (let i = 0; i < stops.length; i += 2)
      pairs.push([stops[i] as number, stops[i + 1] as string])
    expect(pairs[0]).toEqual([0, LEVELS.LOW.color])
    expect(pairs[pairs.length - 1]).toEqual([1, LEVELS.SEVERE.color])
    // Just before 0.4 it is still green; just after it is red.
    const beforeEdge = pairs.filter(([p]) => p <= 0.4 && p > 0.39).map(([, c]) => c)
    const afterEdge = pairs.filter(([p]) => p > 0.4 && p < 0.41).map(([, c]) => c)
    expect(beforeEdge).toContain(LEVELS.LOW.color)
    expect(afterEdge).toContain(LEVELS.SEVERE.color)
  })

  it('always produces strictly increasing positions', () => {
    const many = [
      seg(0, 10, 'LOW'),
      seg(10, 10, 'MODERATE'), // zero length
      seg(10, 55.5, 'HIGH'),
      seg(55.5, 99.9999999, 'SEVERE'),
      seg(99.9999999, 100, 'NO_TRAVEL'),
    ]
    const expression = buildGradient(many, 100)!
    const positions = (expression.slice(3) as (number | string)[]).filter(
      (_, i) => i % 2 === 0,
    ) as number[]
    for (let i = 1; i < positions.length; i++)
      expect(positions[i]).toBeGreaterThan(positions[i - 1])
    expect(positions[0]).toBe(0)
    expect(positions[positions.length - 1]).toBe(1)
  })
})

describe('boundsOf', () => {
  it('boxes all lines together as [[west, south], [east, north]]', () => {
    expect(
      boundsOf([
        [
          [-105, 39.7],
          [-104.8, 41.1],
        ],
        [[-104.2, 40.0]],
      ]),
    ).toEqual([
      [-105, 39.7],
      [-104.2, 41.1],
    ])
  })

  it('is null when there is nothing to box', () => {
    expect(boundsOf([])).toBeNull()
    expect(boundsOf([[]])).toBeNull()
  })
})

describe('resolveSelectedId', () => {
  const routes = makeRoutes(['A', 'B', 'C'])

  it('defaults to the first route before risk is known', () => {
    expect(resolveSelectedId(null, routes, undefined)).toBe('A')
  })

  it('switches to the recommended route once risk arrives', () => {
    expect(resolveSelectedId(null, routes, makeRisk('B', ['A', 'B', 'C']))).toBe('B')
  })

  it("keeps the user's own choice over the recommendation", () => {
    expect(resolveSelectedId('C', routes, makeRisk('B', ['A', 'B', 'C']))).toBe('C')
  })

  it('ignores a choice that no longer exists', () => {
    expect(resolveSelectedId('C', makeRoutes(['A', 'B']), undefined)).toBe('A')
  })

  it('is null without routes', () => {
    expect(resolveSelectedId('A', undefined, undefined)).toBeNull()
  })
})

describe('format', () => {
  it.each([
    [0, '0m'],
    [2700, '45m'],
    [7200, '2h'],
    [95400, '26h 30m'],
    [59, '1m'],
  ])('formatDuration(%i) = %s', (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text)
  })

  it('formats miles with thousands separators', () => {
    expect(formatMiles(1071.3)).toBe('1,071 mi')
    expect(formatMiles(108.5)).toBe('109 mi')
  })
})
