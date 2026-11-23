import type { Route } from '../api/types'

/** The last gap is merged into the destination when it is shorter than this (backend rule). */
const MIN_LAST_GAP_MI = 1

/** How many checkpoints the backend places on a route: mile 0, every `interval` miles, and the
 *  destination (same rule as backend/core/checkpoints.py), so the progress text is the real number. */
export function checkpointCount(distanceMi: number, intervalMi: number): number {
  const regular = Math.max(Math.ceil(distanceMi / intervalMi) - 1, 0) // checkpoints after mile 0
  const lastGap = distanceMi - regular * intervalMi
  const merged = regular > 0 && lastGap < MIN_LAST_GAP_MI ? 1 : 0
  return 1 + regular - merged + 1
}

export function totalCheckpoints(routes: Route[], intervalMi: number): number {
  return routes.reduce((sum, r) => sum + checkpointCount(r.distance_mi, intervalMi), 0)
}
