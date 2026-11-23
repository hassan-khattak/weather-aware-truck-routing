import { describe, expect, it } from 'vitest'
import type { Heatmap } from '../../src/api/types'
import {
  NO_DATA_U16,
  NO_DATA_U8,
  cellAt,
  cellValue,
  decodeHeatmap,
  hourSlice,
} from '../../src/lib/heatmapDecode'
import { latFromMercatorY, mercatorX, mercatorY } from '../../src/lib/mercator'
import { colorFor, legendFor } from '../../src/lib/ramps'
import { sliderLabel } from '../../src/lib/time'

const b64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes))
const f32 = (values: number[]) => b64(new Uint8Array(new Float32Array(values).buffer))
const u8 = (values: number[]) => b64(new Uint8Array(values))
const u16 = (values: number[]) => b64(new Uint8Array(new Uint16Array(values).buffer))

/** Two cells (0.2° grid) and three hours, hour-major. */
function heatmap(): Heatmap {
  return {
    grid_deg: 0.2,
    start_utc: '2026-11-24T21:00:00Z',
    hours: 3,
    cells: f32([40.0, -105.0, 40.2, -105.0]),
    layers: {
      risk: u8([0, 1, 2, NO_DATA_U8, 4, 3]),
      wind: u8([5, 10, 20, 30, NO_DATA_U8, 60]),
      rain: u16([0, 5, 25, NO_DATA_U16, 100, 0]),
      snow: u16([0, 0, 0, 0, 50, 7]),
    },
  }
}

describe('decodeHeatmap', () => {
  it('turns the base64 layers into typed arrays', () => {
    const d = decodeHeatmap(heatmap())
    expect(d.cellCount).toBe(2)
    expect(d.hours).toBe(3)
    expect(d.gridDeg).toBe(0.2)
    expect(Array.from(d.cells)).toEqual([
      expect.closeTo(40.0, 4),
      expect.closeTo(-105.0, 4),
      expect.closeTo(40.2, 4),
      expect.closeTo(-105.0, 4),
    ])
    expect(d.layers.risk).toBeInstanceOf(Uint8Array)
    expect(d.layers.rain).toBeInstanceOf(Uint16Array)
    expect(Array.from(d.layers.rain)).toEqual([0, 5, 25, NO_DATA_U16, 100, 0])
  })

  it('slices one hour as a contiguous run', () => {
    const d = decodeHeatmap(heatmap())
    expect(Array.from(hourSlice(d, 'risk', 1))).toEqual([2, NO_DATA_U8])
    expect(Array.from(hourSlice(d, 'risk', 2))).toEqual([4, 3])
    expect(() => hourSlice(d, 'risk', 3)).toThrow()
  })

  it('reads values in real units and maps the no-data markers to null', () => {
    const d = decodeHeatmap(heatmap())
    expect(cellValue(d, 'risk', 0, 1)).toBe(1)
    expect(cellValue(d, 'wind', 1, 1)).toBe(30)
    expect(cellValue(d, 'rain', 0, 1)).toBeCloseTo(0.05)
    expect(cellValue(d, 'rain', 1, 1)).toBeNull()
    expect(cellValue(d, 'wind', 2, 0)).toBeNull()
  })

  it('finds the cell under a point, if any', () => {
    const d = decodeHeatmap(heatmap())
    expect(cellAt(d, -105.05, 40.05)).toBe(0)
    expect(cellAt(d, -104.95, 40.25)).toBe(1)
    expect(cellAt(d, -105.0, 41.5)).toBeNull()
  })
})

describe('mercator', () => {
  it('round-trips latitude', () => {
    for (const lat of [-60, 0, 25.5, 47.6, 70]) {
      expect(latFromMercatorY(mercatorY(lat))).toBeCloseTo(lat, 8)
    }
  })
  it('puts north at the top and stretches towards the poles', () => {
    expect(mercatorY(48)).toBeLessThan(mercatorY(30))
    const lowGap = mercatorY(30) - mercatorY(31)
    const highGap = mercatorY(47) - mercatorY(48)
    expect(highGap).toBeGreaterThan(lowGap) // a degree is taller on screen further north
    expect(mercatorX(-180)).toBe(0)
    expect(mercatorX(180)).toBe(1)
  })
})

describe('ramps', () => {
  it('leaves missing data transparent', () => {
    expect(colorFor('risk', null)).toBeNull()
    expect(colorFor('wind', null)).toBeNull()
  })
  it('colours risk by level and the others by magnitude', () => {
    const low = colorFor('risk', 0)!
    const severe = colorFor('risk', 3)!
    expect(low).not.toEqual(severe)
    const calm = colorFor('wind', 0)!
    const gale = colorFor('wind', 60)!
    expect(calm[3]).toBeLessThan(gale[3]) // stronger wind is more opaque
    expect(colorFor('wind', 500)).toEqual(gale) // clamped to the top of the ramp
  })
  it('describes each layer for the legend', () => {
    expect(legendFor('wind').unit).toBe('mph')
    expect(legendFor('rain').unit).toBe('in/hr')
    expect(legendFor('risk').stops.map((s) => s.label)).toEqual([
      'Low',
      'Moderate',
      'High',
      'Severe',
      'No Travel',
    ])
  })
})

describe('sliderLabel', () => {
  it('shows the hour offset and the real time in the origin zone', () => {
    expect(sliderLabel('2026-11-24T21:00:00Z', 6, 'America/Chicago')).toBe('+6h · Tue 9:00 PM CST')
    expect(sliderLabel('2026-11-24T21:00:00Z', 0, 'America/Denver')).toBe('+0h · Tue 2:00 PM MST')
  })
  it('follows a daylight-saving change', () => {
    // 11 PM CST + 3h crosses the 2 AM spring-forward, so the clock reads 3 AM CDT.
    expect(sliderLabel('2027-03-14T05:00:00Z', 3, 'America/Chicago')).toBe('+3h · Sun 3:00 AM CDT')
  })
})
