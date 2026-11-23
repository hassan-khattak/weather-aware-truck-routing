import { decode } from '@mapbox/polyline'
import type { Route, RouteRisk } from '../api/types'
import { formatDuration, formatMiles } from '../lib/format'
import { boundsOf, type Bounds, type LngLat } from './bounds'
import { buildGradient } from './gradient'

/** Routes the API can return (plan.md: up to three). Each gets a fixed source and layer. */
export const ROUTE_IDS = ['A', 'B', 'C'] as const

export const sourceId = (id: string) => `route-${id}`
export const layerId = (id: string) => `route-line-${id}`

export const UNSELECTED_COLOR = '#8a94a0'
export const SELECTED_COLOR = '#1d4ed8'
export const SELECTED_WIDTH = 7
export const UNSELECTED_WIDTH = 4

const EMPTY = { type: 'FeatureCollection', features: [] } as const

/** The small part of MapLibre's Map this module uses (so it can be faked in tests). */
export interface MapLike {
  addSource(id: string, source: unknown): unknown
  addLayer(layer: unknown): unknown
  getSource(id: string): { setData(data: unknown): void } | undefined
  setPaintProperty(layer: string, name: string, value: unknown): unknown
  moveLayer(id: string, beforeId?: string): unknown
  fitBounds(bounds: Bounds, options: { padding: unknown; duration?: number }): unknown
  on(type: string, layer: string, listener: (event: LayerMouseEvent) => void): unknown
  getCanvas(): { style: { cursor: string } }
}

export interface LayerMouseEvent {
  lngLat: { lng: number; lat: number }
}

export interface Hover {
  show(routeId: string, at: { lng: number; lat: number }, lines: string[]): void
  hide(): void
}

export interface RouteLayersState {
  routes: Route[]
  risk: RouteRisk[] | undefined
  selectedId: string | null
}

const lineString = (coordinates: LngLat[]) => ({
  type: 'Feature',
  properties: {},
  geometry: { type: 'LineString', coordinates },
})

/** Encoded polyline (lat, lon pairs) to GeoJSON order (lon, lat). */
export function toLngLat(encoded: string): LngLat[] {
  return decode(encoded).map(([lat, lon]) => [lon, lat] as LngLat)
}

/**
 * Owns the route lines on the map. All three sources and layers are created ONCE, when the map is
 * ready; after that a new search only replaces source data, and selecting a route only changes
 * paint properties and layer order. Nothing is ever removed and re-added (no flicker).
 */
export class RouteLayers {
  private readonly map: MapLike
  private readonly onSelect: (routeId: string) => void
  private readonly hover: Hover
  private readonly fitPadding: () => unknown
  private created = false
  private state: RouteLayersState = { routes: [], risk: undefined, selectedId: null }
  private drawnRoutes: Route[] | null = null
  private appliedKey: string | null = null
  private appliedRisk: RouteRisk[] | undefined

  constructor(
    map: MapLike,
    onSelect: (routeId: string) => void,
    hover: Hover,
    fitPadding: () => unknown = () => 40,
  ) {
    this.map = map
    this.onSelect = onSelect
    this.hover = hover
    this.fitPadding = fitPadding
  }

  /** Call once the map style has loaded. Creates the sources and layers, then draws any state
   *  that arrived while the map was still loading. */
  ready(): void {
    if (this.created) return
    this.created = true
    for (const id of ROUTE_IDS) {
      this.map.addSource(sourceId(id), { type: 'geojson', data: EMPTY, lineMetrics: true })
      this.map.addLayer({
        id: layerId(id),
        type: 'line',
        source: sourceId(id),
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': UNSELECTED_COLOR,
          'line-width': UNSELECTED_WIDTH,
          'line-opacity': 0.75,
        },
      })
      this.map.on('click', layerId(id), () => this.onSelect(id))
      this.map.on('mousemove', layerId(id), (event) => {
        this.map.getCanvas().style.cursor = 'pointer'
        this.hover.show(id, event.lngLat, this.hoverLines(id))
      })
      this.map.on('mouseleave', layerId(id), () => {
        this.map.getCanvas().style.cursor = ''
        this.hover.hide()
      })
    }
    this.apply()
  }

  /** Give the latest data. Safe to call at any time, including before the map is ready. */
  update(next: RouteLayersState): void {
    this.state = next
    if (this.created) this.apply()
  }

  private apply(): void {
    const { routes } = this.state
    if (routes !== this.drawnRoutes) this.drawRoutes()
    this.styleRoutes()
  }

  private drawRoutes(): void {
    const { routes } = this.state
    this.drawnRoutes = routes
    this.appliedKey = null
    const lines: LngLat[][] = []
    for (const id of ROUTE_IDS) {
      const route = routes.find((r) => r.id === id)
      const coordinates = route ? toLngLat(route.geometry) : []
      if (route) lines.push(coordinates)
      this.map.getSource(sourceId(id))?.setData(route ? lineString(coordinates) : EMPTY)
    }
    const bounds = boundsOf(lines)
    if (bounds) this.map.fitBounds(bounds, { padding: this.fitPadding(), duration: 600 })
  }

  private styleRoutes(): void {
    const { routes, risk, selectedId } = this.state
    // Skip when nothing relevant changed (selection and risk identity decide the look).
    const key = JSON.stringify([selectedId, risk ? risk.map((r) => r.id) : null, routes.length])
    if (key === this.appliedKey && risk === this.appliedRisk) return
    this.appliedKey = key
    this.appliedRisk = risk

    for (const route of routes) {
      const layer = layerId(route.id)
      if (route.id === selectedId) {
        const gradient = risk ? buildGradient(findSegments(risk, route), route.distance_mi) : null
        this.map.setPaintProperty(layer, 'line-width', SELECTED_WIDTH)
        this.map.setPaintProperty(layer, 'line-opacity', 1)
        this.map.setPaintProperty(layer, 'line-color', SELECTED_COLOR)
        // `null` resets the property, which is how a route stops being risk-coloured.
        this.map.setPaintProperty(layer, 'line-gradient', gradient)
        this.map.moveLayer(layer) // to the top, above the other routes
      } else {
        this.map.setPaintProperty(layer, 'line-width', UNSELECTED_WIDTH)
        this.map.setPaintProperty(layer, 'line-opacity', 0.75)
        this.map.setPaintProperty(layer, 'line-color', UNSELECTED_COLOR)
        this.map.setPaintProperty(layer, 'line-gradient', null)
      }
    }
  }

  private hoverLines(id: string): string[] {
    const route = this.state.routes.find((r) => r.id === id)
    if (!route) return []
    const lines = [
      `Route ${route.id}`,
      `${formatDuration(route.total_s)} · ${formatMiles(route.distance_mi)}`,
    ]
    const summary = this.state.risk?.find((r) => r.id === id)?.summary
    if (summary) {
      const severe = Math.round(summary.miles.SEVERE + summary.miles.NO_TRAVEL)
      const high = Math.round(summary.miles.HIGH)
      lines.push(`${severe} mi Severe or worse · ${high} mi High`)
    }
    return lines
  }
}

function findSegments(risk: RouteRisk[], route: Route) {
  return risk.find((r) => r.id === route.id)?.segments ?? []
}
