/** Request and response shapes of the backend API (see /api/docs/ and plan section 7). */
import type { Level } from '../levels'

export interface Place {
  label: string
  lat: number
  lon: number
  /** IANA zone of the place, e.g. "America/Chicago"; null outside the continental US. */
  tz: string | null
}

export interface PlaceRef {
  label: string
  lat: number
  lon: number
}

export interface RoutesRequest {
  origin: PlaceRef
  destination: PlaceRef
  /** Wall-clock time at the origin, no UTC offset: "2026-11-24T15:00". */
  departure_local: string
  load_lb: number
}

export interface Stop {
  type: 'break' | 'rest'
  mile: number
  start_utc: string
  duration_s: number
}

export interface Route {
  id: string
  order: number
  source: 'api' | 'generated'
  distance_mi: number
  drive_s: number
  total_s: number
  /** Encoded polyline (precision 5), simplified for drawing. */
  geometry: string
  stops: Stop[]
  /** [elapsed seconds, mile] pairs; flat in mile while the truck is parked. */
  timeline: [number, number][]
  long_range_forecast: boolean
}

export interface RoutesResponse {
  trip_id: string
  departure: { utc: string; tz: string; local: string }
  interval_mi: number
  routes: Route[]
  notes: string[]
  warnings: string[]
}

export interface Checkpoint {
  idx: number
  mile: number
  lat: number
  lon: number
  eta_utc: string
  tz: string
  road: string | null
  town: string | null
  town_dist_mi: number | null
  town_dir: string | null
  wind_mph: number | null
  gust_mph: number | null
  rain_in_hr: number | null
  snow_in_hr: number | null
  level: Level
  reasons: string[]
  forecast: boolean
}

export interface Segment {
  from_mi: number
  to_mi: number
  level: Level
}

export interface RouteRisk {
  id: string
  checkpoints: Checkpoint[]
  segments: Segment[]
  summary: { miles: Record<Level, number>; avg_risk: number | null }
}

export interface Recommendation {
  route_id: string
  ranking: string[]
  reason: string
  all_unsafe: boolean
  all_clear: boolean
}

export interface Heatmap {
  grid_deg: number
  start_utc: string
  hours: number
  cells: string
  layers: { risk: string; wind: string; rain: string; snow: string }
}

export interface RiskResponse {
  routes: RouteRisk[]
  recommendation: Recommendation
  heatmap: Heatmap
  weather_as_of: string | null
  stale: boolean
}
