import { describe, expect, it } from 'vitest'
import { decodeHeatmap } from '../../src/lib/heatmapDecode'
import { heatmapHoverLines } from '../../src/lib/heatmapHover'

const b64 = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes))

function data(values: { risk: number; wind: number; rain: number; snow: number }) {
  return decodeHeatmap({
    grid_deg: 0.2,
    start_utc: '2026-11-24T21:00:00Z',
    hours: 1,
    cells: b64(new Uint8Array(new Float32Array([40, -105]).buffer)),
    layers: {
      risk: b64(new Uint8Array([values.risk])),
      wind: b64(new Uint8Array([values.wind])),
      rain: b64(new Uint8Array(new Uint16Array([values.rain]).buffer)),
      snow: b64(new Uint8Array(new Uint16Array([values.snow]).buffer)),
    },
  })
}

describe('heatmapHoverLines', () => {
  it('lists the values with the level in words', () => {
    expect(
      heatmapHoverLines(data({ risk: 2, wind: 38, rain: 5, snow: 0 }), 0, 0, 'America/Chicago'),
    ).toEqual([
      '+0h · Tue 3:00 PM CST',
      'Risk for this truck: High',
      'Wind 38 mph · Rain 0.05 in/hr · Snow 0 in/hr',
    ])
  })
  it('says so when there is no forecast', () => {
    const lines = heatmapHoverLines(
      data({ risk: 255, wind: 255, rain: 65535, snow: 65535 }),
      0,
      0,
      'America/Chicago',
    )
    expect(lines[1]).toBe('No forecast for this area')
  })
})
