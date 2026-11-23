import type { Checkpoint, Route, RouteRisk } from '../api/types'
import { toLngLat, type MapLike } from './routeLayers'
import { EMPTY_FEATURES, checkpointFeatures, highlightFeatures, markerFeatures } from './features'

export const HIGHLIGHT_LAYER = 'checkpoint-highlight'
export const MARKER_LAYER = 'route-markers'
export const DOT_LAYER = 'checkpoint-dots'

const HIGHLIGHT_SOURCE = 'checkpoint-highlight'
const MARKER_SOURCE = 'route-markers'
const DOT_SOURCE = 'checkpoint-dots'

export interface CheckpointHandlers {
  /** The pointer is over a dot (idx), or left them (null). */
  onHover(idx: number | null, at?: { lng: number; lat: number }): void
  onPick(idx: number): void
}

export interface CheckpointLayersState {
  route: Route | undefined
  risk: RouteRisk | undefined
  activeIdx: number | null
}

/**
 * The selected route's checkpoint dots, its origin/destination/stop markers and the ring around
 * the active checkpoint. Like the route lines, sources and layers are created once; a new route or
 * selection only replaces their data.
 */
export class CheckpointLayers {
  private readonly map: MapLike
  private readonly handlers: CheckpointHandlers
  private created = false
  private state: CheckpointLayersState = { route: undefined, risk: undefined, activeIdx: null }
  private drawn: { route?: Route; checkpoints?: Checkpoint[] } = {}

  constructor(map: MapLike, handlers: CheckpointHandlers) {
    this.map = map
    this.handlers = handlers
  }

  /** Call once the style has loaded, BEFORE the route lines are created, so the lines can be
   *  inserted below these layers. */
  ready(): void {
    if (this.created) return
    this.created = true
    for (const id of [HIGHLIGHT_SOURCE, MARKER_SOURCE, DOT_SOURCE]) {
      this.map.addSource(id, { type: 'geojson', data: EMPTY_FEATURES })
    }
    this.map.addLayer({
      id: HIGHLIGHT_LAYER,
      type: 'circle',
      source: HIGHLIGHT_SOURCE,
      paint: {
        'circle-radius': 13,
        'circle-color': '#ffffff',
        'circle-opacity': 0.9,
        'circle-stroke-width': 3,
        'circle-stroke-color': '#111827',
      },
    })
    this.map.addLayer({
      id: MARKER_LAYER,
      type: 'circle',
      source: MARKER_SOURCE,
      paint: {
        'circle-radius': ['match', ['get', 'kind'], ['origin', 'destination'], 8, 6],
        'circle-color': [
          'match',
          ['get', 'kind'],
          'origin',
          '#111827',
          'destination',
          '#ffffff',
          'break',
          '#0e7490',
          '#7c3aed',
        ],
        'circle-stroke-width': 3,
        'circle-stroke-color': ['match', ['get', 'kind'], 'destination', '#111827', '#ffffff'],
      },
    })
    this.map.addLayer({
      id: DOT_LAYER,
      type: 'circle',
      source: DOT_SOURCE,
      paint: {
        'circle-radius': 6,
        'circle-color': ['get', 'color'],
        'circle-stroke-width': ['case', ['get', 'heavy'], 3, 1.5],
        'circle-stroke-color': ['case', ['get', 'heavy'], '#111827', '#ffffff'],
      },
    })
    this.map.on('mousemove', DOT_LAYER, (event) => {
      this.map.getCanvas().style.cursor = 'pointer'
      const idx = idxOf(event)
      if (idx !== null) this.handlers.onHover(idx, event.lngLat)
    })
    this.map.on('mouseleave', DOT_LAYER, () => {
      this.map.getCanvas().style.cursor = ''
      this.handlers.onHover(null)
    })
    this.map.on('click', DOT_LAYER, (event) => {
      const idx = idxOf(event)
      if (idx !== null) this.handlers.onPick(idx)
    })
    this.apply()
  }

  update(next: CheckpointLayersState): void {
    this.state = next
    if (this.created) this.apply()
  }

  private apply(): void {
    const { route, risk, activeIdx } = this.state
    const checkpoints = risk?.checkpoints
    if (route !== this.drawn.route) {
      this.drawn.route = route
      const line = route ? toLngLat(route.geometry) : []
      this.map
        .getSource(MARKER_SOURCE)
        ?.setData(route ? markerFeatures(route, line) : EMPTY_FEATURES)
    }
    if (checkpoints !== this.drawn.checkpoints) {
      this.drawn.checkpoints = checkpoints
      this.map
        .getSource(DOT_SOURCE)
        ?.setData(checkpoints ? checkpointFeatures(checkpoints) : EMPTY_FEATURES)
    }
    this.map.getSource(HIGHLIGHT_SOURCE)?.setData(highlightFeatures(checkpoints ?? [], activeIdx))
  }
}

function idxOf(event: { features?: { properties?: Record<string, unknown> }[] }): number | null {
  const idx = event.features?.[0]?.properties?.idx
  return typeof idx === 'number' ? idx : null
}
