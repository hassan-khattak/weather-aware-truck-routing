import { LEVELS, type Level } from '../levels'
import type { LayerName } from './heatmapDecode'

/** [r, g, b, alpha 0–1]. */
export type Rgba = [number, number, number, number]

const RISK_ORDER: Level[] = ['LOW', 'MODERATE', 'HIGH', 'SEVERE', 'NO_TRAVEL']
const RISK_ALPHA = 0.45

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

interface Ramp {
  title: string
  unit: string
  max: number
  rgb: [number, number, number]
}

// One hue each; the value sets the opacity, so calm weather fades away and the corridor stays clear.
const RAMPS: Record<Exclude<LayerName, 'risk'>, Ramp> = {
  wind: { title: 'Wind', unit: 'mph', max: 60, rgb: [13, 148, 136] },
  rain: { title: 'Rain', unit: 'in/hr', max: 0.5, rgb: [37, 99, 235] },
  snow: { title: 'Snow', unit: 'in/hr', max: 0.5, rgb: [124, 58, 237] },
}
const MIN_ALPHA = 0.08
const MAX_ALPHA = 0.7

/** The colour of a value on a layer; null (nothing drawn) where there is no data. */
export function colorFor(layer: LayerName, value: number | null): Rgba | null {
  if (value === null) return null
  if (layer === 'risk') {
    const level = RISK_ORDER[Math.min(Math.max(Math.round(value), 0), RISK_ORDER.length - 1)]
    return [...hexToRgb(LEVELS[level].color), RISK_ALPHA]
  }
  const ramp = RAMPS[layer]
  const t = Math.min(Math.max(value / ramp.max, 0), 1)
  return [...ramp.rgb, MIN_ALPHA + (MAX_ALPHA - MIN_ALPHA) * t]
}

export interface LegendStop {
  label: string
  color: string
}

export interface Legend {
  title: string
  unit: string
  stops: LegendStop[]
}

const css = ([r, g, b, a]: Rgba) => `rgba(${r}, ${g}, ${b}, ${a})`

export function legendFor(layer: LayerName): Legend {
  if (layer === 'risk') {
    return {
      title: 'Risk for this truck',
      unit: '',
      stops: RISK_ORDER.map((level) => ({
        label: LEVELS[level].label,
        color: css(colorFor('risk', RISK_ORDER.indexOf(level))!),
      })),
    }
  }
  const ramp = RAMPS[layer]
  const marks = [0, 0.25, 0.5, 1]
  return {
    title: ramp.title,
    unit: ramp.unit,
    stops: marks.map((t) => ({
      label: String(Number((ramp.max * t).toFixed(2))),
      color: css(colorFor(layer, ramp.max * t)!),
    })),
  }
}
