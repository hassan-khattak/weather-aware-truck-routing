import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { HeatmapBitmaps } from '../../src/map/heatmapBitmaps'
import { HEATMAP_LAYER, HEATMAP_SOURCE, HeatmapLayer } from '../../src/map/heatmapLayer'

function setup() {
  const source = { setCoordinates: vi.fn(), play: vi.fn(), pause: vi.fn() }
  const renders: (() => void)[] = []
  const map = {
    addSource: vi.fn(),
    addLayer: vi.fn(),
    getSource: vi.fn(() => source),
    setLayoutProperty: vi.fn(),
    triggerRepaint: vi.fn(),
    once: vi.fn((_type: string, listener: () => void) => renders.push(listener)),
  }
  const ctx = {
    globalAlpha: 1,
    alphas: [] as number[],
    clearRect: vi.fn(),
    drawImage: vi.fn(function (this: { alphas: number[]; globalAlpha: number }) {
      this.alphas.push(this.globalAlpha)
    }),
  }
  const canvas = { width: 0, height: 0, getContext: () => ctx }
  const bitmaps = {
    geometry: {
      width: 300,
      height: 200,
      coordinates: [
        [-106, 41],
        [-104, 41],
        [-104, 39],
        [-106, 39],
      ],
    },
    maxHour: 48,
    get: vi.fn((layer: string, hour: number) => ({ layer, hour })),
    precompute: vi.fn(),
  }
  const layer = new HeatmapLayer(map, () => canvas)
  return {
    map,
    source,
    renders,
    ctx,
    canvas,
    bitmaps: bitmaps as unknown as HeatmapBitmaps,
    layer,
    raw: bitmaps,
  }
}

describe('HeatmapLayer', () => {
  let t: ReturnType<typeof setup>
  beforeEach(() => {
    t = setup()
  })

  it('creates one canvas source and one raster layer, once', () => {
    t.layer.ready('route-line-A')
    t.layer.ready('route-line-A')
    t.layer.setBitmaps(t.bitmaps)
    t.layer.show(5)
    expect(t.map.addSource).toHaveBeenCalledTimes(1)
    expect(t.map.addSource.mock.calls[0][1]).toMatchObject({ type: 'canvas', animate: false })
    expect(t.map.addLayer).toHaveBeenCalledTimes(1)
    expect(t.map.addLayer.mock.calls[0][0]).toMatchObject({ id: HEATMAP_LAYER, type: 'raster' })
    expect(t.map.addLayer.mock.calls[0][1]).toBe('route-line-A')
    expect(HEATMAP_SOURCE).toBe('heatmap')
  })

  it('sizes the canvas and places it on the corridor, even if data arrived before the map', () => {
    t.layer.setBitmaps(t.bitmaps) // map not ready yet
    t.layer.ready()
    expect(t.canvas.width).toBe(300)
    expect(t.canvas.height).toBe(200)
    expect(t.source.setCoordinates).toHaveBeenCalledWith(t.raw.geometry.coordinates)
  })

  it('draws the picture of the shown hour for the current layer', () => {
    t.layer.ready()
    t.layer.setBitmaps(t.bitmaps)
    t.layer.show(12)
    expect(t.raw.get).toHaveBeenLastCalledWith('risk', 12)
    t.layer.setLayer('wind')
    expect(t.raw.precompute).toHaveBeenCalledWith('wind')
    expect(t.raw.get).toHaveBeenLastCalledWith('wind', 12)
  })

  it('cross-fades two hours for a fractional time', () => {
    t.layer.ready()
    t.layer.setBitmaps(t.bitmaps)
    t.ctx.alphas.length = 0
    t.layer.show(12.25)
    expect(t.ctx.alphas).toEqual([0.75, 0.25])
    expect(t.raw.get).toHaveBeenCalledWith('risk', 12)
    expect(t.raw.get).toHaveBeenCalledWith('risk', 13)
  })

  it('clamps to the forecast window', () => {
    t.layer.ready()
    t.layer.setBitmaps(t.bitmaps)
    t.layer.show(99)
    expect(t.raw.get).toHaveBeenLastCalledWith('risk', 48)
    t.layer.show(-3)
    expect(t.raw.get).toHaveBeenLastCalledWith('risk', 0)
  })

  it('hides and shows with the layout visibility, without recreating anything', () => {
    t.layer.ready()
    t.layer.setVisible(false)
    expect(t.map.setLayoutProperty).toHaveBeenLastCalledWith(HEATMAP_LAYER, 'visibility', 'none')
    t.layer.setVisible(true)
    expect(t.map.setLayoutProperty).toHaveBeenLastCalledWith(HEATMAP_LAYER, 'visibility', 'visible')
    expect(t.map.addLayer).toHaveBeenCalledTimes(1)
  })

  it('has MapLibre copy the canvas for one frame after a change, then stops', () => {
    t.layer.ready()
    t.layer.setBitmaps(t.bitmaps)
    t.source.play.mockClear()
    t.layer.show(3)
    t.layer.show(4) // two changes in the same frame
    expect(t.source.play).toHaveBeenCalled()
    expect(t.map.once).toHaveBeenCalledTimes(1) // one pending render, never one per change
    t.renders.forEach((render) => render())
    expect(t.source.pause).toHaveBeenCalled()
  })

  it('keeps copying every frame while playing', () => {
    t.layer.ready()
    t.layer.setBitmaps(t.bitmaps)
    t.layer.setPlaying(true)
    t.source.pause.mockClear()
    t.layer.show(7.5)
    t.renders.forEach((render) => render())
    expect(t.source.pause).not.toHaveBeenCalled()
    t.layer.setPlaying(false)
    expect(t.source.pause).toHaveBeenCalled()
  })
})
