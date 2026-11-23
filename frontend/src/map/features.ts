import type { Checkpoint, Route } from '../api/types'
import { haversineMi } from '../lib/geo'
import { HIGH_AND_ABOVE, LEVELS } from '../levels'
import type { LngLat } from './bounds'

export interface Feature {
  type: 'Feature'
  properties: Record<string, string | number | boolean>
  geometry: { type: 'Point'; coordinates: LngLat }
}

export interface FeatureCollection {
  type: 'FeatureCollection'
  features: Feature[]
}

export const EMPTY_FEATURES: FeatureCollection = { type: 'FeatureCollection', features: [] }

const point = ([lon, lat]: LngLat, properties: Feature['properties']): Feature => ({
  type: 'Feature',
  properties,
  geometry: { type: 'Point', coordinates: [lon, lat] },
})

/** One feature per checkpoint; `heavy` marks High and above, which get a thicker ring. */
export function checkpointFeatures(checkpoints: Checkpoint[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: checkpoints.map((cp) =>
      point([cp.lon, cp.lat], {
        idx: cp.idx,
        level: cp.level,
        color: LEVELS[cp.level].color,
        heavy: HIGH_AND_ABOVE.has(cp.level),
      }),
    ),
  }
}

/** Miles from the start of the line to each of its points (computed once per route). */
export function cumulativeMiles(line: LngLat[]): number[] {
  const lengths = [0]
  for (let i = 1; i < line.length; i++) {
    const [lon1, lat1] = line[i - 1]
    const [lon2, lat2] = line[i]
    lengths.push(lengths[i - 1] + haversineMi({ lat: lat1, lon: lon1 }, { lat: lat2, lon: lon2 }))
  }
  return lengths
}

/** The point `mile` miles along a line, scaling the line's own length to the route distance
 *  (the drawn line is simplified, so its length is only approximately the route's). Pass
 *  `lengths` (from `cumulativeMiles`) when asking many times for the same line. */
export function pointAtMile(
  line: LngLat[],
  mile: number,
  totalMi: number,
  lengths: number[] = cumulativeMiles(line),
): LngLat {
  if (line.length === 0) return [0, 0]
  const total = lengths[lengths.length - 1]
  if (total === 0 || totalMi <= 0) return line[0]
  const target = Math.min(Math.max(mile / totalMi, 0), 1) * total
  let i = 1
  while (i < lengths.length - 1 && lengths[i] < target) i++
  const span = lengths[i] - lengths[i - 1]
  const t = span === 0 ? 0 : (target - lengths[i - 1]) / span
  const [lon1, lat1] = line[i - 1]
  const [lon2, lat2] = line[i]
  return [lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t]
}

/** Origin, destination, and the required breaks and rests of a route. */
export function markerFeatures(route: Route, line: LngLat[]): FeatureCollection {
  if (line.length === 0) return EMPTY_FEATURES
  const features = [
    point(line[0], { kind: 'origin' }),
    point(line[line.length - 1], { kind: 'destination' }),
    ...route.stops.map((stop) =>
      point(pointAtMile(line, stop.mile, route.distance_mi), { kind: stop.type }),
    ),
  ]
  return { type: 'FeatureCollection', features }
}

/** The ring that highlights the active checkpoint. */
export function highlightFeatures(
  checkpoints: Checkpoint[],
  idx: number | null,
): FeatureCollection {
  const cp = idx === null ? undefined : checkpoints.find((c) => c.idx === idx)
  return cp
    ? { type: 'FeatureCollection', features: [point([cp.lon, cp.lat], { idx: cp.idx })] }
    : EMPTY_FEATURES
}
