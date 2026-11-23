import { LEVELS, type Level } from '../levels'
import { cellValue, type DecodedHeatmap } from './heatmapDecode'
import { sliderLabel } from './time'

const RISK_BY_ORDINAL: Level[] = ['LOW', 'MODERATE', 'HIGH', 'SEVERE', 'NO_TRAVEL']

const trimmed = (value: number) => String(Number(value.toFixed(2)))

/** What the weather is in a heatmap cell at an hour: all four values, with the level in words. */
export function heatmapHoverLines(
  d: DecodedHeatmap,
  hour: number,
  cell: number,
  zone: string,
): string[] {
  const risk = cellValue(d, 'risk', hour, cell)
  const wind = cellValue(d, 'wind', hour, cell)
  const rain = cellValue(d, 'rain', hour, cell)
  const snow = cellValue(d, 'snow', hour, cell)
  const title = sliderLabel(d.startUtc, hour, zone)
  if (risk === null || wind === null || rain === null || snow === null) {
    return [title, 'No forecast for this area']
  }
  const level = LEVELS[RISK_BY_ORDINAL[Math.min(Math.round(risk), RISK_BY_ORDINAL.length - 1)]]
  return [
    title,
    `Risk for this truck: ${level.label}`,
    `Wind ${Math.round(wind)} mph · Rain ${trimmed(rain)} in/hr · Snow ${trimmed(snow)} in/hr`,
  ]
}
