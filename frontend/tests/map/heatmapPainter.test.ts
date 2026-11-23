import { describe, expect, it, vi } from 'vitest'
import type { Heatmap } from '../../src/api/types'
import { decodeHeatmap } from '../../src/lib/heatmapDecode'
import { mercatorY } from '../../src/lib/mercator'
import { HeatmapBitmaps } from '../../src/map/heatmapBitmaps'
import {
  canvasGeometry,
  latAtRow,
  paintHour,
  type Context2D,
  type Surface,
} from '../../src/map/heatmapPainter'

const b64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes))
const f32 = (v: number[]) => b64(new Uint8Array(new Float32Array(v).buffer))
const u8 = (v: number[]) => b64(new Uint8Array(v))
const u16 = (v: number[]) => b64(new Uint8Array(new Uint16Array(v).buffer))

/** A tall north–south corridor (Seattle → Chicago is the real case), two hours. */
function tall(): Heatmap {
  const cells = [30, 40, 47].flatMap((lat) => [lat, -100])
  const n = cells.length / 2
  return {
    grid_deg: 0.2,
    start_utc: '2026-11-24T21:00:00Z',
    hours: 2,
    cells: f32(cells),
    layers: {
      risk: u8(Array.from({ length: 2 * n }, (_, i) => i % 5)),
      wind: u8(Array.from({ length: 2 * n }, () => 20)),
      rain: u16(Array.from({ length: 2 * n }, () => 0)),
      snow: u16(Array.from({ length: 2 * n }, () => 0)),
    },
  }
}

function fakeSurface() {
  const surfaces: { ctx: Context2D & { rects: number[][] }; source: object }[] = []
  const make = (width: number, height: number): Surface => {
    const ctx = {
      fillStyle: '',
      filter: undefined as string | undefined,
      globalAlpha: 1,
      rects: [] as number[][],
      fillRect(x: number, y: number, w: number, h: number) {
        this.rects.push([x, y, w, h])
      },
      clearRect() {},
      drawImage: vi.fn(),
    }
    const surface = { ctx, source: { width, height } }
    surfaces.push(surface)
    return surface as unknown as Surface
  }
  return { make, surfaces }
}

describe('canvasGeometry', () => {
  it('is linear in Mercator y and caps its size', () => {
    const g = canvasGeometry(decodeHeatmap(tall()))
    expect(Math.max(g.width, g.height)).toBeLessThanOrEqual(1024)
    // Rows are Mercator rows: the middle row is NOT the middle latitude.
    const middle = latAtRow(g, g.height / 2)
    const midLat = (g.coordinates[0][1] + g.coordinates[2][1]) / 2
    expect(middle).toBeGreaterThan(midLat)
  })
  it('gives the corners for a MapLibre canvas source', () => {
    const g = canvasGeometry(decodeHeatmap(tall()))
    const [tl, tr, br, bl] = g.coordinates
    expect(tl[1]).toBe(tr[1])
    expect(bl[1]).toBe(br[1])
    expect(tl[0]).toBe(bl[0])
    expect(tl[1]).toBeGreaterThan(bl[1])
  })
})

describe('paintHour', () => {
  it('places each cell by Mercator y, not by latitude', () => {
    const d = decodeHeatmap(tall())
    const g = canvasGeometry(d)
    const { make, surfaces } = fakeSurface()
    paintHour(d, 'wind', 0, g, make)
    const rects = surfaces[0].ctx.rects
    expect(rects).toHaveLength(3)
    const centreY = (r: number[]) => r[1] + r[3] / 2
    const expected = (lat: number) =>
      ((mercatorY(lat) - g.box.y0) / (g.box.y1 - g.box.y0)) * g.height
    // rects follow the cell order: lat 30, 40, 47 → rows go up the canvas (smaller y)
    expect(centreY(rects[0])).toBeCloseTo(expected(30), 0)
    expect(centreY(rects[1])).toBeCloseTo(expected(40), 0)
    expect(centreY(rects[2])).toBeCloseTo(expected(47), 0)
  })

  it('skips cells with no data and softens the result with a blur', () => {
    const raw = tall()
    raw.layers.wind = u8([255, 255, 255, 255, 255, 255])
    const d = decodeHeatmap(raw)
    const { make, surfaces } = fakeSurface()
    paintHour(d, 'wind', 0, canvasGeometry(d), make)
    expect(surfaces[0].ctx.rects).toHaveLength(0)
    expect(surfaces[1].ctx.filter).toMatch(/^blur\(/)
    expect(surfaces[1].ctx.drawImage).toHaveBeenCalledTimes(1)
  })
})

describe('HeatmapBitmaps', () => {
  function setup() {
    const { make } = fakeSurface()
    const tasks: (() => void)[] = []
    const toBitmap = vi.fn(async (source: unknown) => ({ bitmap: source, close: vi.fn() }))
    const bitmaps = new HeatmapBitmaps(decodeHeatmap(tall()), {
      schedule: (task) => tasks.push(task),
      makeSurface: make,
      toBitmap: toBitmap as never,
    })
    return { bitmaps, tasks, toBitmap }
  }

  it('paints an hour on demand and reuses it', () => {
    const { bitmaps } = setup()
    const first = bitmaps.get('risk', 1)
    expect(bitmaps.get('risk', 1)).toBe(first)
  })

  it('converts all hours to bitmaps one per idle slot', async () => {
    const { bitmaps, tasks, toBitmap } = setup()
    bitmaps.precompute('risk')
    expect(toBitmap).not.toHaveBeenCalled() // nothing runs until the browser is idle
    while (tasks.length) tasks.shift()!()
    await Promise.resolve()
    expect(toBitmap).toHaveBeenCalledTimes(2) // two hours
    expect(bitmaps.has('risk', 0)).toBe(true)
  })

  it('stops the old layer when a new one is requested', () => {
    const { bitmaps, tasks, toBitmap } = setup()
    bitmaps.precompute('risk')
    bitmaps.precompute('wind')
    while (tasks.length) tasks.shift()!()
    expect(toBitmap).toHaveBeenCalledTimes(2) // only the wind layer's two hours
  })

  it('keeps two layers and frees older ones', () => {
    const { bitmaps } = setup()
    bitmaps.get('risk', 0)
    bitmaps.get('wind', 0)
    bitmaps.get('rain', 0)
    expect(bitmaps.has('risk', 0)).toBe(false)
    expect(bitmaps.has('wind', 0)).toBe(true)
    expect(bitmaps.has('rain', 0)).toBe(true)
  })
})
