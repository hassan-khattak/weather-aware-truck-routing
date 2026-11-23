import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  RouteLayers,
  SELECTED_COLOR,
  SELECTED_WIDTH,
  UNSELECTED_COLOR,
  UNSELECTED_WIDTH,
  layerId,
  sourceId,
  toLngLat,
  type Hover,
  type LayerMouseEvent,
  type MapLike,
} from '../../src/map/routeLayers'
import { LINE_A, makeRisk, makeRoutes } from '../fixtures'

class FakeMap implements MapLike {
  sources: Record<string, { type: string; lineMetrics?: boolean }> = {}
  layers: { id: string; source: string }[] = []
  data: Record<string, unknown> = {}
  paint: Record<string, Record<string, unknown>> = {}
  handlers: Record<string, (event: LayerMouseEvent) => void> = {}
  canvas = { style: { cursor: '' } }

  addSource = vi.fn((id: string, source: { type: string; lineMetrics?: boolean }) => {
    this.sources[id] = source
  })
  addLayer = vi.fn((layer: { id: string; source: string }) => {
    this.layers.push(layer)
  })
  getSource = vi.fn((id: string) => ({
    setData: (data: unknown) => {
      this.data[id] = data
      this.setDataCalls.push(id)
    },
  }))
  setDataCalls: string[] = []
  setPaintProperty = vi.fn((layer: string, name: string, value: unknown) => {
    ;(this.paint[layer] ??= {})[name] = value
  })
  moveLayer = vi.fn()
  fitBounds = vi.fn()
  on = vi.fn((type: string, layer: string, listener: (event: LayerMouseEvent) => void) => {
    this.handlers[`${type}:${layer}`] = listener
  })
  getCanvas() {
    return this.canvas
  }
}

let map: FakeMap
let onSelect: ReturnType<typeof vi.fn<(routeId: string) => void>>
let hover: { show: ReturnType<typeof vi.fn>; hide: ReturnType<typeof vi.fn> }
let layers: RouteLayers

beforeEach(() => {
  map = new FakeMap()
  onSelect = vi.fn<(routeId: string) => void>()
  hover = { show: vi.fn(), hide: vi.fn() }
  layers = new RouteLayers(map, onSelect, hover as Hover, () => ({
    top: 1,
    left: 2,
    right: 3,
    bottom: 4,
  }))
})

const state = (over: Partial<Parameters<RouteLayers['update']>[0]> = {}) => ({
  routes: makeRoutes().routes,
  risk: undefined,
  selectedId: 'A',
  ...over,
})

describe('creation', () => {
  it('touches nothing until the map is ready', () => {
    layers.update(state())
    expect(map.addSource).not.toHaveBeenCalled()
    expect(map.addLayer).not.toHaveBeenCalled()
    expect(map.fitBounds).not.toHaveBeenCalled()
  })

  it('creates one source and one layer per route slot, with line metrics for the gradient', () => {
    layers.ready()
    expect(Object.keys(map.sources)).toEqual(['route-A', 'route-B', 'route-C'])
    expect(Object.values(map.sources).every((s) => s.type === 'geojson' && s.lineMetrics)).toBe(
      true,
    )
    expect(map.layers.map((l) => [l.id, l.source])).toEqual([
      ['route-line-A', 'route-A'],
      ['route-line-B', 'route-B'],
      ['route-line-C', 'route-C'],
    ])
  })

  it('draws state that arrived before the map was ready', () => {
    layers.update(state())
    layers.ready()
    expect(map.data[sourceId('A')]).toMatchObject({
      geometry: { type: 'LineString' },
    })
    expect(map.setDataCalls).toEqual(['route-A', 'route-B', 'route-C'])
  })

  it('is safe to call ready twice', () => {
    layers.ready()
    layers.ready()
    expect(map.addSource).toHaveBeenCalledTimes(3)
  })
})

describe('drawing routes', () => {
  beforeEach(() => layers.ready())

  it('converts the polyline to GeoJSON order (longitude first)', () => {
    layers.update(state())
    const line = (map.data[sourceId('A')] as { geometry: { coordinates: number[][] } }).geometry
      .coordinates
    expect(line[0]).toEqual([-104.99, 39.74])
    expect(line).toHaveLength(LINE_A.length)
    expect(toLngLat('_p~iF~ps|U_ulLnnqC_mqNvxq`@')[0]).toEqual([-120.2, 38.5])
  })

  it('fits the map to all routes, once per new set of routes', () => {
    layers.update(state())
    expect(map.fitBounds).toHaveBeenCalledTimes(1)
    const [bounds, options] = map.fitBounds.mock.calls[0]
    expect(bounds[0][0]).toBeCloseTo(-105.0, 3) // west
    expect(bounds[0][1]).toBeCloseTo(39.74, 3) // south
    expect(bounds[1][1]).toBeCloseTo(41.14, 3) // north
    expect(options.padding).toEqual({ top: 1, left: 2, right: 3, bottom: 4 })
  })

  it('animates the fit by default and not at all when the duration is 0 (reduced motion)', () => {
    layers.ready()
    layers.update(state())
    expect(map.fitBounds.mock.calls[0][1].duration).toBe(600)

    const calm = new FakeMap()
    const still = new RouteLayers(
      calm,
      onSelect,
      hover as Hover,
      () => 10,
      () => 0,
    )
    still.ready()
    still.update(state())
    expect(calm.fitBounds.mock.calls[0][1].duration).toBe(0)
  })

  it('clears slots that a new search does not use', () => {
    layers.update(state({ routes: makeRoutes(['A', 'B', 'C']).routes }))
    layers.update(state({ routes: makeRoutes(['A']).routes }))
    expect(map.data[sourceId('B')]).toMatchObject({ features: [] })
    expect(map.data[sourceId('C')]).toMatchObject({ features: [] })
  })
})

describe('never adding or removing layers again', () => {
  it('only updates data and paint after creation, across searches and selections', () => {
    layers.ready()
    const routes = makeRoutes(['A', 'B', 'C']).routes
    layers.update(state({ routes, selectedId: 'A' }))
    layers.update(state({ routes, selectedId: 'B' }))
    layers.update(state({ routes, selectedId: 'C', risk: makeRisk('C', ['A', 'B', 'C']).routes }))
    layers.update(state({ routes: makeRoutes(['A', 'B']).routes, selectedId: 'A' }))
    layers.update(state({ routes: [], selectedId: null }))

    expect(map.addSource).toHaveBeenCalledTimes(3)
    expect(map.addLayer).toHaveBeenCalledTimes(3)
    expect('removeLayer' in map).toBe(false) // the controller cannot even ask for it
  })

  it('selecting a route does not redraw data or move the map', () => {
    layers.ready()
    const routes = makeRoutes().routes
    layers.update(state({ routes, selectedId: 'A' }))
    const draws = map.setDataCalls.length
    const fits = map.fitBounds.mock.calls.length
    layers.update(state({ routes, selectedId: 'B' }))
    expect(map.setDataCalls.length).toBe(draws)
    expect(map.fitBounds.mock.calls.length).toBe(fits)
  })
})

describe('selection styling', () => {
  beforeEach(() => layers.ready())

  it('makes the selected route bold, solid and on top, and the others faded grey', () => {
    layers.update(state({ selectedId: 'B' }))
    expect(map.paint[layerId('B')]).toMatchObject({
      'line-width': SELECTED_WIDTH,
      'line-opacity': 1,
      'line-color': SELECTED_COLOR,
    })
    expect(map.paint[layerId('A')]).toMatchObject({
      'line-width': UNSELECTED_WIDTH,
      'line-color': UNSELECTED_COLOR,
    })
    expect(map.moveLayer).toHaveBeenLastCalledWith(layerId('B'))
  })

  it('is neutral (no gradient) until risk is known', () => {
    layers.update(state())
    expect(map.paint[layerId('A')]['line-gradient']).toBeNull()
  })

  it('colours only the selected route from its risk segments once risk arrives', () => {
    const risk = makeRisk('A').routes
    layers.update(state({ risk, selectedId: 'A' }))
    const gradient = map.paint[layerId('A')]['line-gradient'] as unknown[]
    expect(gradient[0]).toBe('interpolate')
    expect(map.paint[layerId('B')]['line-gradient']).toBeNull()
  })

  it('moves the gradient when the selection changes', () => {
    const risk = makeRisk('A').routes
    layers.update(state({ risk, selectedId: 'A' }))
    layers.update(state({ risk, selectedId: 'B' }))
    expect(map.paint[layerId('A')]['line-gradient']).toBeNull()
    expect(Array.isArray(map.paint[layerId('B')]['line-gradient'])).toBe(true)
  })

  it('does no work when nothing changed', () => {
    const risk = makeRisk('A').routes
    const routes = makeRoutes().routes
    layers.update(state({ routes, risk, selectedId: 'A' }))
    const calls = map.setPaintProperty.mock.calls.length
    layers.update(state({ routes, risk, selectedId: 'A' }))
    expect(map.setPaintProperty.mock.calls.length).toBe(calls)
  })
})

describe('interaction', () => {
  beforeEach(() => {
    layers.ready()
    layers.update(state({ risk: makeRisk('A').routes }))
  })

  it('selects a route when its line is clicked', () => {
    map.handlers[`click:${layerId('B')}`]({ lngLat: { lng: -104.8, lat: 40 } })
    expect(onSelect).toHaveBeenCalledWith('B')
  })

  it('shows a mini summary on hover and a pointer cursor, and hides it on leave', () => {
    map.handlers[`mousemove:${layerId('A')}`]({ lngLat: { lng: -104.9, lat: 40.1 } })
    expect(map.canvas.style.cursor).toBe('pointer')
    const [id, at, lines] = hover.show.mock.calls[0]
    expect(id).toBe('A')
    expect(at).toEqual({ lng: -104.9, lat: 40.1 })
    expect(lines[0]).toBe('Route A')
    expect(lines[1]).toBe('1h 55m · 109 mi')
    expect(lines[2]).toMatch(/mi Severe or worse/)

    map.handlers[`mouseleave:${layerId('A')}`]({ lngLat: { lng: 0, lat: 0 } })
    expect(map.canvas.style.cursor).toBe('')
    expect(hover.hide).toHaveBeenCalled()
  })

  it('omits the risk line from the hover before risk is known', () => {
    layers.update(state({ risk: undefined }))
    map.handlers[`mousemove:${layerId('B')}`]({ lngLat: { lng: -104.9, lat: 40.1 } })
    expect(hover.show.mock.calls[0][2]).toHaveLength(2)
  })
})
