import type { Route } from '../api/types'
import type { LngLat } from './bounds'
import { pointAtMile } from './features'

export type TruckState = 'driving' | 'parked' | 'arrived' | 'beyond-window'

export interface Truck {
  state: TruckState
  mile: number
  position: LngLat
}

/** Mile reached after `elapsedS` seconds, interpolating the route's [seconds, mile] timeline. */
function mileAt(timeline: [number, number][], elapsedS: number): { mile: number; parked: boolean } {
  if (timeline.length === 0) return { mile: 0, parked: false }
  if (elapsedS <= timeline[0][0]) return { mile: timeline[0][1], parked: false }
  for (let i = 1; i < timeline.length; i++) {
    const [t0, m0] = timeline[i - 1]
    const [t1, m1] = timeline[i]
    if (elapsedS <= t1) {
      const parked = m1 === m0
      const t = t1 === t0 ? 1 : (elapsedS - t0) / (t1 - t0)
      return { mile: m0 + (m1 - m0) * t, parked }
    }
  }
  return { mile: timeline[timeline.length - 1][1], parked: false }
}

/**
 * Where the truck is `elapsedS` seconds after departure. It stays put while parked at a stop,
 * and when the trip is longer than the forecast window it says so at the end of the window.
 */
export function truckAt(
  route: Route,
  line: LngLat[],
  elapsedS: number,
  windowS: number = Infinity,
  lengths?: number[],
): Truck {
  if (elapsedS >= route.total_s) {
    return { state: 'arrived', mile: route.distance_mi, position: line[line.length - 1] ?? [0, 0] }
  }
  const { mile, parked } = mileAt(route.timeline, elapsedS)
  const position = pointAtMile(line, mile, route.distance_mi, lengths)
  if (elapsedS >= windowS) return { state: 'beyond-window', mile, position }
  return { state: parked ? 'parked' : 'driving', mile, position }
}
