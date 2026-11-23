import { LEVELS } from '../levels'
import type { Segment } from '../api/types'

/** A MapLibre expression (loosely typed: the style spec types are very strict for gradients). */
export type GradientExpression = unknown[]

// Colour stops need strictly increasing positions, so a hard edge is two stops a hair apart.
const EDGE = 1e-6

/**
 * Colours a route line stretch by stretch with `line-gradient` (needs `lineMetrics: true` on the
 * source). `segments` come from the API as miles along the route; `line-progress` runs 0..1 along
 * the drawn line, so positions are miles divided by the route length.
 */
export function buildGradient(segments: Segment[], distanceMi: number): GradientExpression | null {
  if (segments.length === 0 || distanceMi <= 0) return null

  const stops: [number, string][] = []
  segments.forEach((segment, index) => {
    const color = LEVELS[segment.level].color
    const start = index === 0 ? 0 : Math.min(segment.from_mi / distanceMi, 1 - EDGE)
    const end = index === segments.length - 1 ? 1 : Math.min(segment.to_mi / distanceMi, 1 - EDGE)
    stops.push([start, color], [end, color])
  })

  // Make positions strictly increasing: a boundary shared by two segments becomes a hard edge.
  const cleaned: [number, string][] = []
  for (const [position, color] of stops) {
    const last = cleaned[cleaned.length - 1]
    if (last && position <= last[0]) {
      if (last[1] === color) continue // same colour at the same spot: nothing to add
      cleaned.push([last[0] + EDGE, color])
    } else if (!last || last[1] !== color || position !== last[0]) {
      cleaned.push([position, color])
    }
  }
  if (cleaned.length < 2) cleaned.push([1, cleaned[0][1]])

  return ['interpolate', ['linear'], ['line-progress'], ...cleaned.flat()]
}
