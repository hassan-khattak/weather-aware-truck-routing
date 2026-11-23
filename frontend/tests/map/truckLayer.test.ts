import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TRUCK_LAYER, TRUCK_SOURCE, TruckLayer } from '../../src/map/truckLayer'
import { LINE_A, makeRoute } from '../fixtures'

const route = makeRoute('A', LINE_A, {
  distance_mi: 100,
  total_s: 10800,
  drive_s: 7200,
  timeline: [
    [0, 0],
    [3600, 50],
    [7200, 50],
    [10800, 100],
  ],
})

function setup() {
  const sent: {
    features: { properties: { state: string }; geometry: { coordinates: number[] } }[]
  }[] = []
  const map = {
    addSource: vi.fn(),
    addLayer: vi.fn(),
    getSource: vi.fn(() => ({ setData: (d: never) => sent.push(d) })),
  }
  const frames: (() => void)[] = []
  const layer = new TruckLayer(map, (cb) => frames.push(cb))
  const flush = () => frames.splice(0).forEach((cb) => cb())
  return { map, layer, sent, flush, frames }
}

describe('TruckLayer', () => {
  let t: ReturnType<typeof setup>
  beforeEach(() => {
    t = setup()
    t.layer.ready()
    t.layer.ready()
  })

  it('creates its source and layer once', () => {
    expect(t.map.addSource).toHaveBeenCalledTimes(1)
    expect(t.map.addLayer).toHaveBeenCalledTimes(1)
    expect(t.map.addLayer.mock.calls[0][0]).toMatchObject({ id: TRUCK_LAYER, source: TRUCK_SOURCE })
  })

  it('shows nothing until there is a route', () => {
    t.sent.length = 0
    t.layer.show(3)
    t.flush()
    expect(t.sent.at(-1)).toMatchObject({ features: [] })
  })

  it('places the truck from the timeline and parks it at a stop', () => {
    t.layer.setRoute(route, 48)
    t.layer.show(0)
    t.flush()
    const start = t.sent.at(-1)!.features[0]
    expect(start.properties.state).toBe('driving')
    t.layer.show(1.5) // 5400 s: parked at mile 50 until 7200 s
    t.flush()
    const parked = t.sent.at(-1)!.features[0]
    t.layer.show(1.9)
    t.flush()
    expect(parked.properties.state).toBe('parked')
    expect(t.sent.at(-1)!.features[0].geometry.coordinates).toEqual(parked.geometry.coordinates)
    t.layer.show(5)
    t.flush()
    expect(t.sent.at(-1)!.features[0].properties.state).toBe('arrived')
  })

  it('coalesces many updates into one write per frame', () => {
    t.layer.setRoute(route, 48)
    t.flush()
    t.sent.length = 0
    for (let h = 0; h < 30; h++) t.layer.show(h / 10)
    expect(t.frames).toHaveLength(1)
    t.flush()
    expect(t.sent).toHaveLength(1)
  })
})
