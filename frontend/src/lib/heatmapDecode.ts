import type { Heatmap } from '../api/types'

export const NO_DATA_U8 = 255
export const NO_DATA_U16 = 65535

export type LayerName = 'risk' | 'wind' | 'rain' | 'snow'

export interface DecodedHeatmap {
  gridDeg: number
  startUtc: string
  hours: number
  cellCount: number
  /** [lat, lon, lat, lon, …] of the cell centres. */
  cells: Float32Array
  /** Hour-major: index = hour * cellCount + cell. */
  layers: { risk: Uint8Array; wind: Uint8Array; rain: Uint16Array; snow: Uint16Array }
}

function bytesOf(text: string): Uint8Array<ArrayBuffer> {
  const binary = atob(text)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

// Typed arrays over a fresh buffer: the API sends little-endian values, as every browser expects.
const floats = (text: string) => new Float32Array(bytesOf(text).buffer)
const shorts = (text: string) => new Uint16Array(bytesOf(text).buffer)

/** Decode the base64 layers once, when the risk response arrives. */
export function decodeHeatmap(h: Heatmap): DecodedHeatmap {
  const cells = floats(h.cells)
  return {
    gridDeg: h.grid_deg,
    startUtc: h.start_utc,
    hours: h.hours,
    cellCount: cells.length / 2,
    cells,
    layers: {
      risk: bytesOf(h.layers.risk),
      wind: bytesOf(h.layers.wind),
      rain: shorts(h.layers.rain),
      snow: shorts(h.layers.snow),
    },
  }
}

/** One hour of one layer: a view, not a copy. */
export function hourSlice(d: DecodedHeatmap, layer: LayerName, hour: number) {
  if (!Number.isInteger(hour) || hour < 0 || hour >= d.hours) {
    throw new RangeError(`hour ${hour} is outside 0..${d.hours - 1}`)
  }
  return d.layers[layer].subarray(hour * d.cellCount, (hour + 1) * d.cellCount)
}

/** A cell's value in real units (mph, in/hr, or the risk level 0–4); null where there is no data. */
export function cellValue(
  d: DecodedHeatmap,
  layer: LayerName,
  hour: number,
  cell: number,
): number | null {
  const raw = hourSlice(d, layer, hour)[cell]
  if (layer === 'rain' || layer === 'snow') return raw === NO_DATA_U16 ? null : raw / 100
  return raw === NO_DATA_U8 ? null : raw
}

const lookups = new WeakMap<DecodedHeatmap, Map<string, number>>()
const key = (latIdx: number, lonIdx: number) => `${latIdx},${lonIdx}`

/** The cell whose square contains the point, or null outside the corridor. */
export function cellAt(d: DecodedHeatmap, lng: number, lat: number): number | null {
  let index = lookups.get(d)
  if (!index) {
    index = new Map()
    for (let i = 0; i < d.cellCount; i++) {
      index.set(
        key(Math.round(d.cells[2 * i] / d.gridDeg), Math.round(d.cells[2 * i + 1] / d.gridDeg)),
        i,
      )
    }
    lookups.set(d, index)
  }
  return index.get(key(Math.round(lat / d.gridDeg), Math.round(lng / d.gridDeg))) ?? null
}
