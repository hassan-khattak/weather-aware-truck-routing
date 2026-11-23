import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Checkpoint } from '../../src/api/types'
import {
  CheckpointLayers,
  type CheckpointHandlers,
  DOT_LAYER,
  HIGHLIGHT_LAYER,
} from '../../src/map/checkpointLayers'
import {
  checkpointFeatures,
  highlightFeatures,
  markerFeatures,
  pointAtMile,
} from '../../src/map/features'
import { RouteLayers, layerId, type Hover, type LayerMouseEvent } from '../../src/map/routeLayers'
import { LINE_A, makeRoute, makeRouteRisk } from '../fixtures'

function cp(idx: number, level: Checkpoint['level'] = 'LOW'): Checkpoint {
  return {
    idx,
    mile: idx * 10,
    lat: 39.74 + idx * 0.1,
    lon: -104.99,
    eta_utc: '2026-11-24T21:00:00Z',
    tz: 'America/Denver',
    road: null,
    town: null,
    town_dist_mi: null,
    town_dir: null,
    wind_mph: 5,
    gust_mph: 8,
    rain_in_hr: 0,
    snow_in_hr: 0,
    level,
    reasons: [],
    forecast: true,
  }
}

describe('features', () => {
  it('gives every checkpoint its level colour and marks High and above as heavy', () => {
    const { features } = checkpointFeatures([cp(0, 'LOW'), cp(1, 'HIGH'), cp(2, 'SEVERE')])
    expect(features.map((f) => f.properties.heavy)).toEqual([false, true, true])
    expect(features[0].properties).toMatchObject({ idx: 0, level: 'LOW', color: '#1a7f37' })
    expect(features[1].geometry.coordinates).toEqual([-104.99, 39.84])
  })

  it('finds points along a line by mile', () => {
    const line: [number, number][] = [
      [-105, 40],
      [-105, 41],
    ]
    expect(pointAtMile(line, 0, 69)).toEqual([-105, 40])
    expect(pointAtMile(line, 69, 69)).toEqual([-105, 41])
    const [lon, lat] = pointAtMile(line, 34.5, 69)
    expect(lon).toBe(-105)
    expect(lat).toBeCloseTo(40.5, 3)
    expect(pointAtMile(line, 500, 69)).toEqual([-105, 41]) // clamped
  })

  it('marks origin, destination and each stop', () => {
    const route = makeRoute('A', LINE_A, {
      stops: [{ type: 'break', mile: 50, start_utc: '2026-11-24T23:00:00Z', duration_s: 1800 }],
    })
    const line = LINE_A.map(([lat, lon]) => [lon, lat] as [number, number])
    const kinds = markerFeatures(route, line).features.map((f) => f.properties.kind)
    expect(kinds).toEqual(['origin', 'destination', 'break'])
    expect(markerFeatures(route, []).features).toEqual([])
  })

  it('highlights only a known checkpoint', () => {
    expect(highlightFeatures([cp(0), cp(1)], 1).features).toHaveLength(1)
    expect(highlightFeatures([cp(0)], null).features).toEqual([])
    expect(highlightFeatures([cp(0)], 9).features).toEqual([])
  })
})

class FakeMap {
  layers: string[] = []
  data: Record<string, unknown> = {}
  handlers: Record<string, (event: LayerMouseEvent) => void> = {}
  canvas = { style: { cursor: '' } }
  addSource = vi.fn()
  addLayer = vi.fn((layer: { id: string }, before?: string) => {
    this.layers.push(`${layer.id}${before ? `<${before}` : ''}`)
  })
  getSource = vi.fn((id: string) => ({ setData: (d: unknown) => (this.data[id] = d) }))
  setPaintProperty = vi.fn()
  moveLayer = vi.fn()
  fitBounds = vi.fn()
  on = vi.fn((type: string, layer: string, l: (e: LayerMouseEvent) => void) => {
    this.handlers[`${type}:${layer}`] = l
  })
  getCanvas() {
    return this.canvas
  }
}

describe('CheckpointLayers', () => {
  let map: FakeMap
  let handlers: {
    onHover: ReturnType<typeof vi.fn<CheckpointHandlers['onHover']>>
    onPick: ReturnType<typeof vi.fn<CheckpointHandlers['onPick']>>
  }
  let layers: CheckpointLayers
  const route = makeRoute('A', LINE_A)
  const risk = { ...makeRouteRisk('A'), checkpoints: [cp(0), cp(1, 'SEVERE')] }

  beforeEach(() => {
    map = new FakeMap()
    handlers = {
      onHover: vi.fn<CheckpointHandlers['onHover']>(),
      onPick: vi.fn<CheckpointHandlers['onPick']>(),
    }
    layers = new CheckpointLayers(map, handlers)
    layers.ready()
  })

  it('creates its layers once, however often the data changes', () => {
    layers.update({ route, risk, activeIdx: null })
    layers.update({ route, risk, activeIdx: 1 })
    layers.update({ route: undefined, risk: undefined, activeIdx: null })
    layers.ready()
    expect(map.addLayer).toHaveBeenCalledTimes(3)
  })

  it('shows no dots until risk arrives, then the selected route dots', () => {
    layers.update({ route, risk: undefined, activeIdx: null })
    expect(map.data['checkpoint-dots']).toBeUndefined() // still the empty initial data
    expect(map.data['route-markers']).toMatchObject({ features: expect.any(Array) })
    layers.update({ route, risk, activeIdx: null })
    expect((map.data['checkpoint-dots'] as { features: unknown[] }).features).toHaveLength(2)
  })

  it('moves the highlight ring to the active checkpoint', () => {
    layers.update({ route, risk, activeIdx: 1 })
    const ring = map.data['checkpoint-highlight'] as { features: { properties: { idx: number } }[] }
    expect(ring.features[0].properties.idx).toBe(1)
  })

  it('reports hover, leave and click from the dots', () => {
    const event = (idx: number): LayerMouseEvent => ({
      lngLat: { lng: -105, lat: 40 },
      features: [{ properties: { idx } }],
    })
    map.handlers[`mousemove:${DOT_LAYER}`](event(1))
    expect(handlers.onHover).toHaveBeenLastCalledWith(1, { lng: -105, lat: 40 })
    map.handlers[`mouseleave:${DOT_LAYER}`](event(1))
    expect(handlers.onHover).toHaveBeenLastCalledWith(null)
    map.handlers[`click:${DOT_LAYER}`](event(1))
    expect(handlers.onPick).toHaveBeenCalledWith(1)
  })
})

describe('route lines stay below the dots', () => {
  it('inserts and raises lines relative to the anchor layer', () => {
    const map = new FakeMap()
    const hover: Hover = { show: vi.fn(), hide: vi.fn() }
    const lines = new RouteLayers(
      map,
      vi.fn(),
      hover,
      () => 0,
      () => 0,
      HIGHLIGHT_LAYER,
    )
    lines.ready()
    expect(map.layers).toEqual([
      `${layerId('A')}<${HIGHLIGHT_LAYER}`,
      `${layerId('B')}<${HIGHLIGHT_LAYER}`,
      `${layerId('C')}<${HIGHLIGHT_LAYER}`,
    ])
    lines.update({ routes: [makeRoute('A', LINE_A)], risk: undefined, selectedId: 'A' })
    expect(map.moveLayer).toHaveBeenLastCalledWith(layerId('A'), HIGHLIGHT_LAYER)
  })
})
