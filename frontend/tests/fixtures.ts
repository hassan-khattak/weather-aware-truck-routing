import { encode } from '@mapbox/polyline'
import type { Level } from '../src/levels'
import type { RiskResponse, Route, RouteRisk, RoutesResponse } from '../src/api/types'

/** [lat, lon] polylines, roughly Denver -> Cheyenne by two different roads. */
export const LINE_A: [number, number][] = [
  [39.74, -104.99],
  [40.4, -105.0],
  [41.14, -104.82],
]
export const LINE_B: [number, number][] = [
  [39.74, -104.99],
  [40.4, -104.7],
  [41.14, -104.82],
]

export function makeRoute(id: string, line: [number, number][], over: Partial<Route> = {}): Route {
  return {
    id,
    order: id.charCodeAt(0) - 65,
    source: 'api',
    distance_mi: 108.5,
    drive_s: 6900,
    total_s: 6900,
    geometry: encode(line),
    stops: [],
    timeline: [
      [0, 0],
      [6900, 108.5],
    ],
    long_range_forecast: false,
    ...over,
  }
}

export function makeRoutes(ids: string[] = ['A', 'B']): RoutesResponse {
  const lines: Record<string, [number, number][]> = { A: LINE_A, B: LINE_B, C: LINE_B }
  return {
    trip_id: 't_test',
    departure: { utc: '2026-11-24T21:00:00Z', tz: 'America/Denver', local: '2026-11-24T14:00' },
    interval_mi: 10,
    routes: ids.map((id) => makeRoute(id, lines[id])),
    notes: [],
    warnings: [],
  }
}

export function makeRouteRisk(id: string, levels: Level[] = ['LOW', 'HIGH']): RouteRisk {
  const miles = {
    LOW: 0,
    MODERATE: 0,
    HIGH: 0,
    SEVERE: 0,
    NO_TRAVEL: 0,
    NO_FORECAST: 0,
  } as Record<Level, number>
  const each = 108.5 / levels.length
  const segments = levels.map((level, i) => {
    miles[level] += each
    return { from_mi: i * each, to_mi: (i + 1) * each, level }
  })
  return { id, checkpoints: [], segments, summary: { miles, avg_risk: 0.5 } }
}

export function makeRisk(recommended = 'A', ids: string[] = ['A', 'B']): RiskResponse {
  return {
    routes: ids.map((id) => makeRouteRisk(id)),
    recommendation: {
      route_id: recommended,
      ranking: ids,
      reason: '0 Severe mi vs 25 on Route X; +18 min',
      all_unsafe: false,
      all_clear: false,
    },
    heatmap: {
      grid_deg: 0.2,
      start_utc: '2026-11-24T21:00:00Z',
      hours: 49,
      cells: '',
      layers: { risk: '', wind: '', rain: '', snow: '' },
    },
    weather_as_of: '2026-11-24T18:00:00Z',
    stale: false,
  }
}
